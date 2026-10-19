"""Live integration in a NEW database + NEW Pinecone namespace. Never migrates the source DB."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='storage/integration/latest')
    parser.add_argument('--limit', type=int, default=8, help='0 runs all 52 synthetic questions')
    parser.add_argument('--resume', action='store_true', help='Reuse this isolated run after correcting a dependency')
    parser.add_argument('--judge', action='store_true', help='Additional Groq calls to judge each answer')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv('.env')
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL, make_url
    from src.evaluation.fixtures import generate
    from src.evaluation.run import score
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'run.json'
    if args.resume:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    else:
        if manifest_path.exists():
            raise RuntimeError('Output already contains a run. Use --resume or another --output')
        identifier = secrets.token_hex(6)
        manifest = {'database': 'codex_v1_test_' + identifier, 'namespace': 'integration-' + identifier,
                    'kind': 'synthetic_integration', 'checks': {}}
    db_name = manifest['database']
    if not db_name.startswith('codex_v1_test_') or not db_name.replace('_', '').isalnum():
        raise RuntimeError('Invalid isolated database name')
    url = make_url(os.environ['DATABASE_URL']) if os.getenv('DATABASE_URL') else URL.create(
        'mysql+pymysql', username=os.getenv('MYSQL_USER'), password=os.getenv('MYSQL_PASSWORD'),
        host=os.getenv('MYSQL_HOST'), port=int(os.getenv('MYSQL_PORT', '3306')), database=os.getenv('MYSQL_DB'))
    isolated_url = url.set(database=db_name)
    if not args.resume:
        admin = create_engine(url, connect_args={'connect_timeout': 10})
        with admin.begin() as connection:
            connection.execute(text(f'CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
        admin.dispose()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        bootstrap = create_engine(isolated_url)
        sql = Path('mysql.sql').read_text(encoding='utf-8')
        with bootstrap.begin() as connection:
            for statement in sql.split(';'):
                if statement.strip():
                    connection.execute(text(statement))
        bootstrap.dispose()
    # Overrides apply only to this process and its worker. Never write credentials into artifacts.
    os.environ['DATABASE_URL'] = isolated_url.render_as_string(hide_password=False)
    os.environ['PINECONE_NAMESPACE'] = manifest['namespace']
    os.environ['DOCUMENT_STORAGE_DIR'] = str(root / 'originals')
    os.environ['EMBEDDING_BACKEND'] = os.getenv('INTEGRATION_EMBEDDING_BACKEND', 'local-onnx')
    os.environ['GROQ_MODEL'] = os.getenv('GROQ_MODEL') or 'openai/gpt-oss-20b'
    os.environ['LLM_TEMPERATURE'] = '0'
    os.environ['GROQ_REQUEST_INTERVAL'] = '5'
    manifest['embedding_backend'] = os.environ['EMBEDDING_BACKEND']
    manifest['model'] = os.environ['GROQ_MODEL']

    from src.config.database import get_database_engine
    get_database_engine.cache_clear()
    from src.config.migrate import main as migrate
    from src.config.db_session import engine
    migrate()
    migrate()  # Verify migration repeatability on real MySQL.
    manifest['checks']['migration_idempotent'] = True
    files, cases = generate(root / 'fixtures')
    from src.utils.embedding_utils import get_embeddings
    print('Loading embedding model...', flush=True)
    get_embeddings('Integration preflight')
    manifest['checks']['embedding'] = True
    from src.app import app
    from werkzeug.serving import make_server, WSGIRequestHandler
    import requests
    class QuietHandler(WSGIRequestHandler):
        def log_request(self, code='-', size='-'):
            pass
    server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/api'
    workers = []
    log = None
    try:
        if not manifest.get('user_id'):
            email = 'integration-' + secrets.token_hex(6) + '@example.com'
            password = secrets.token_urlsafe(32)
            response = requests.post(base+'/register', json={'email': email, 'password': password}, timeout=30)
            response.raise_for_status()
            login = requests.post(base+'/login', json={'email': email, 'password': password}, timeout=30)
            login.raise_for_status()
            manifest['user_id'] = login.json()['user']['id']
            token = login.json()['access_token']
        else:
            from flask_jwt_extended import create_access_token
            with app.app_context():
                token = create_access_token(identity=str(manifest['user_id']))
        headers = {'Authorization': 'Bearer '+token}
        response = requests.post(base+'/conversations/new', headers=headers, json={'title': 'Integration upload'}, timeout=30)
        response.raise_for_status()
        conversation = response.json()['conversation_id']
        documents = {}
        for filename in files:
            with (root/'fixtures'/filename).open('rb') as handle:
                response = requests.post(base+f'/conversations/{conversation}/documents', headers=headers,
                                         files={'files': (filename, handle)}, timeout=30)
            if response.status_code != 202:
                raise RuntimeError('Upload failed: '+filename+' HTTP '+str(response.status_code))
            documents[filename] = response.json()['results'][0]['document_id']
        manifest['documents'] = documents
        manifest['checks']['upload_all_formats'] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        log = (root/'worker.log').open('a', encoding='utf-8')
        workers = [subprocess.Popen([sys.executable, '-m', 'src.workers.ingestion'],
                    stdout=log, stderr=log, env=os.environ.copy()) for _ in range(2)]
        deadline = time.monotonic() + 240
        while True:
            states = {}
            for filename, doc in documents.items():
                response = requests.get(base+f'/documents/{doc}/status', headers=headers, timeout=20)
                response.raise_for_status()
                states[filename] = response.json()['status']
            print('Document states:', json.dumps(states), flush=True)
            if all(state == 'ready' for state in states.values()):
                break
            if any(state == 'failed' for state in states.values()) or time.monotonic() > deadline:
                raise RuntimeError('Ingestion did not complete; inspect isolated worker.log')
            time.sleep(3)
        manifest['checks']['worker_all_ready'] = True
        manifest['checks']['concurrent_workers'] = 2
        # Prove duplicate upload returns the existing document.
        filename = files[0]
        with (root/'fixtures'/filename).open('rb') as handle:
            duplicate = requests.post(base+f'/conversations/{conversation}/documents', headers=headers,
                                      files={'files': (filename, handle)}, timeout=30)
        manifest['checks']['deduplication'] = duplicate.json()['results'][0]['document_id'] == documents[filename]
        # Independent conversation per question prevents benchmark history contamination.
        selected = cases if args.limit == 0 else cases[:args.limit]
        if args.limit == 8:
            selected = [next(c for c in cases if c['category'] == ext) for ext in ['pdf','docx','txt','md','csv','xlsx']]+cases[-2:]
        for case in selected:
            response = requests.post(base+'/conversations/new', headers=headers, json={'title': case['id']}, timeout=30)
            response.raise_for_status()
            cid = response.json()['conversation_id']
            with engine.begin() as connection:
                for filename in case['filenames']:
                    connection.execute(text('INSERT INTO ConversationDocuments (ConversationID,DocumentID) VALUES (:cid,:doc)'),
                                       {'cid': cid, 'doc': documents[filename]})
            case['conversation_id'] = cid
            case['document_ids'] = [documents[name] for name in case['filenames']]
        dataset_path = root/'dataset.jsonl'
        dataset_path.write_text(''.join(json.dumps(c, ensure_ascii=False)+'\n' for c in selected), encoding='utf-8')
        def query(case):
            response = requests.post(base+'/chat', headers=headers, json={
                'query_text': case['question'], 'conversation_id': case['conversation_id'],
                'document_ids': case['document_ids']}, timeout=180)
            if response.status_code != 200:
                return {'id': case['id'], 'error': 'HTTP '+str(response.status_code)}
            trace = requests.get(base+'/chat/traces/'+response.json()['trace_id'], headers=headers, timeout=20)
            trace.raise_for_status()
            return {'id': case['id'], **trace.json()}
        predictions = []
        with (root/'predictions.jsonl').open('w', encoding='utf-8') as handle:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(query, case): case for case in selected}
                for future in as_completed(futures):
                    case = futures[future]
                    try:
                        value = future.result()
                    except Exception as exc:
                        value = {'id': case['id'], 'error': type(exc).__name__}
                    predictions.append(value)
                    handle.write(json.dumps(value, ensure_ascii=False)+'\n')
                    handle.flush()
                    print(f"Chat {len(predictions)}/{len(selected)}: {case['id']} {'FAILED' if value.get('error') else 'OK'}", flush=True)
        report = score(selected, predictions, use_judge=args.judge)
        report['metadata'] = {'corpus': 'synthetic', 'model': manifest['model'],
            'embedding_backend': manifest['embedding_backend'], 'namespace': manifest['namespace'],
            'note': 'Integration result; not evidence of domain-quality or a before/after improvement.'}
        (root/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest['checks']['chat_error_rate'] = report['overall']['error_rate']
        manifest['report'] = str(root/'report.json')
        print('Report:',json.dumps(report['overall']),flush=True)
        if report['overall']['error_rate']:
            raise RuntimeError('Some live chat cases failed; see report')
    finally:
        for worker in workers:
            worker.terminate()
            worker.wait(timeout=15)
        if log is not None:
            log.close()
        server.shutdown()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Isolated run saved to:',str(root),flush=True)


if __name__ == '__main__':
    main()
