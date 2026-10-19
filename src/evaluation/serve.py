"""Run the upgraded backend/worker against a previously created isolated test database."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_directory')
    args = parser.parse_args()
    root = Path(args.run_directory).resolve()
    manifest = json.loads((root/'run.json').read_text(encoding='utf-8'))
    if not manifest['database'].startswith('codex_v1_test_') or not manifest['namespace'].startswith('integration-'):
        raise RuntimeError('Only isolated test databases/namespaces are allowed')
    from dotenv import load_dotenv
    load_dotenv('.env')
    from sqlalchemy.engine import URL, make_url
    url = make_url(os.environ['DATABASE_URL']) if os.getenv('DATABASE_URL') else URL.create(
        'mysql+pymysql', username=os.getenv('MYSQL_USER'), password=os.getenv('MYSQL_PASSWORD'),
        host=os.getenv('MYSQL_HOST'), port=int(os.getenv('MYSQL_PORT', '3306')), database=os.getenv('MYSQL_DB'))
    os.environ.update(DATABASE_URL=url.set(database=manifest['database']).render_as_string(hide_password=False),
        PINECONE_NAMESPACE=manifest['namespace'], EMBEDDING_BACKEND=manifest['embedding_backend'],
        DOCUMENT_STORAGE_DIR=str(root/'originals'), GROQ_MODEL=manifest['model'], GROQ_REQUEST_INTERVAL='5')
    from src.config.database import get_database_engine
    get_database_engine.cache_clear()
    from src.config.migrate import main as migrate
    migrate()
    from src.app import app
    worker = subprocess.Popen([sys.executable, '-m', 'src.workers.ingestion'],
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        print('Isolated backend: http://127.0.0.1:5000 ; Ctrl+C stops backend and worker.',flush=True)
        app.run(host='127.0.0.1', port=5000, use_reloader=False)
    finally:
        worker.terminate()
        worker.wait(timeout=15)


if __name__ == '__main__':
    main()
