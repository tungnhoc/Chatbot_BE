"""Exercise the built Next.js proxies against the isolated backend on localhost."""
import argparse
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_directory')
    parser.add_argument('--frontend', required=True)
    args = parser.parse_args()
    root = Path(args.run_directory).resolve()
    frontend = Path(args.frontend).resolve()
    manifest = json.loads((root/'run.json').read_text(encoding='utf-8'))
    if not manifest['database'].startswith('codex_v1_test_') or not manifest['namespace'].startswith('integration-'):
        raise RuntimeError('Only isolated runs are allowed')
    from dotenv import load_dotenv
    load_dotenv('.env')
    from sqlalchemy.engine import URL, make_url
    url = make_url(os.environ['DATABASE_URL']) if os.getenv('DATABASE_URL') else URL.create(
        'mysql+pymysql', username=os.getenv('MYSQL_USER'), password=os.getenv('MYSQL_PASSWORD'),
        host=os.getenv('MYSQL_HOST'), port=int(os.getenv('MYSQL_PORT', '3306')), database=os.getenv('MYSQL_DB'))
    os.environ.update(DATABASE_URL=url.set(database=manifest['database']).render_as_string(hide_password=False),
        PINECONE_NAMESPACE=manifest['namespace'], EMBEDDING_BACKEND=manifest['embedding_backend'],
        GROQ_MODEL=manifest['model'], LLM_TEMPERATURE='0', GROQ_REQUEST_INTERVAL='5')
    from src.config.database import get_database_engine
    get_database_engine.cache_clear()
    from src.config.migrate import main as migrate
    migrate()
    from src.app import app
    from flask_jwt_extended import create_access_token
    from werkzeug.serving import make_server, WSGIRequestHandler
    import requests
    class Quiet(WSGIRequestHandler):
        def log_request(self, code='-', size='-'):
            pass
    server = make_server('127.0.0.1', 5000, app, threaded=True, request_handler=Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = None
    checks = {}
    try:
        with (root/'frontend-server.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([shutil.which('node'), str(frontend/'node_modules/next/dist/bin/next'),
                'start','-p','3007'], cwd=frontend, stdout=log, stderr=log,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            base = 'http://127.0.0.1:3007'
            for _ in range(30):
                try:
                    if requests.get(base, timeout=2).status_code == 200:
                        break
                except requests.ConnectionError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError('Next.js did not start; see frontend-server.log')
            with app.app_context():
                token = create_access_token(identity=str(manifest['user_id']))
                foreign = create_access_token(identity='999999')
            headers = {'Authorization': 'Bearer '+token}
            denied = requests.get(base+'/api/chat/documents/1/status',timeout=10)
            checks['status_requires_auth'] = denied.status_code == 401
            response = requests.post(base+'/api/chat/conversations/new', headers=headers, json={'title':'Frontend integration'}, timeout=15)
            response.raise_for_status()
            cid = response.json()['conversation_id']
            filename = 'catalog_3.txt'
            with (root/'fixtures'/filename).open('rb') as handle:
                response = requests.post(base+f'/api/chat/upload-file/{cid}', headers=headers,
                    files={'files':(filename,handle)}, timeout=20)
            checks['upload_preserves_202'] = response.status_code == 202
            response.raise_for_status()
            doc = response.json()['uploaded'][0]['document_id']
            status = requests.get(base+f'/api/chat/documents/{doc}/status',headers=headers,timeout=10)
            checks['status_ready'] = status.status_code == 200 and status.json()['status'] == 'ready'
            files = requests.get(base+f'/api/chat/load-files/{cid}',headers=headers,timeout=10)
            checks['list_files'] = files.status_code == 200 and files.json()['files'][0]['filename'] == filename
            denied = requests.get(base+f'/api/chat/documents/{doc}/status',headers={'Authorization':'Bearer '+foreign},timeout=10)
            checks['foreign_status_denied'] = denied.status_code == 404
            retry = requests.post(base+f'/api/chat/documents/{doc}/retry',headers=headers,timeout=10)
            checks['ready_document_retry_rejected'] = retry.status_code == 404
            response = requests.post(base+'/api/chat/send-message',headers=headers,
                json={'conversationId':cid,'message':'What is the price of P31 in VND?','documentIds':[doc]},timeout=180)
            response.raise_for_status()
            reply = response.json()
            checks['chat_sources'] = bool(reply.get('sources')) and bool(reply.get('trace_id'))
            history = requests.get(base+f'/api/chat/history/{cid}',headers=headers,timeout=10)
            history.raise_for_status()
            checks['history_keeps_sources'] = bool(history.json()['messages'][-1]['sources'])
            checks['history_keeps_trace'] = history.json()['messages'][-1]['trace_id'] == reply['trace_id']
            (root/'frontend-smoke.json').write_text(json.dumps({'checks':checks,'all_passed':all(checks.values()),
                'conversation_id':cid,'note':'HTTP integration of built Next.js proxy routes, not a visual browser test.'},indent=2),encoding='utf-8')
            print(json.dumps(checks),flush=True)
            if not all(checks.values()):
                raise RuntimeError('Some frontend proxy checks failed')
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=15)
        server.shutdown()


if __name__ == '__main__':
    main()
