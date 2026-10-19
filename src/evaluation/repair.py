"""Retry failed cases in an isolated run, preserving original measurements."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_directory')
    args = parser.parse_args()
    root = Path(args.run_directory).resolve()
    manifest = json.loads((root/'run.json').read_text(encoding='utf-8'))
    if not manifest['database'].startswith('codex_v1_test_') or not manifest['namespace'].startswith('integration-'):
        raise RuntimeError('Repair is restricted to isolated integration runs')
    from dotenv import load_dotenv
    load_dotenv('.env')
    from sqlalchemy.engine import URL, make_url
    original = make_url(os.environ['DATABASE_URL']) if os.getenv('DATABASE_URL') else URL.create(
        'mysql+pymysql', username=os.getenv('MYSQL_USER'), password=os.getenv('MYSQL_PASSWORD'),
        host=os.getenv('MYSQL_HOST'), port=int(os.getenv('MYSQL_PORT', '3306')), database=os.getenv('MYSQL_DB'))
    os.environ.update(DATABASE_URL=original.set(database=manifest['database']).render_as_string(hide_password=False),
        PINECONE_NAMESPACE=manifest['namespace'], EMBEDDING_BACKEND=manifest['embedding_backend'],
        GROQ_MODEL=manifest['model'], LLM_TEMPERATURE='0', GROQ_REQUEST_INTERVAL='5')
    from src.config.database import get_database_engine
    get_database_engine.cache_clear()
    from src.config.migrate import main as migrate
    migrate()
    from src.evaluation.run import read_jsonl, score
    from src.evaluation.metrics import judge_answer
    from src.config.db_session import SessionLocal
    from src.services.chat_service import handle_chat_query
    from sqlalchemy import text
    cases = read_jsonl(root/'dataset.jsonl')
    predictions = {p['id']: p for p in read_jsonl(root/'predictions.jsonl')}
    old_report = json.loads((root/'report.json').read_text(encoding='utf-8'))
    old_scores = {r['id']: r for r in old_report['cases']}
    replaced = set()
    for case in cases:
        if not predictions.get(case['id'], {}).get('error'):
            continue
        session = SessionLocal()
        try:
            response = handle_chat_query(session, str(manifest['user_id']), case['question'],
                                         case['conversation_id'], case['document_ids'])
            value = session.execute(text('SELECT Payload FROM ChatTraces WHERE TraceID=:id'), {'id': response['trace_id']}).scalar_one()
            payload = json.loads(value) if isinstance(value, str) else value
            predictions[case['id']] = {'id': case['id'], **payload}
            replaced.add(case['id'])
            print('Recovered:',ascii(case['id']),flush=True)
        except Exception as error:
            print('Still failed:',ascii(case['id']),type(error).__name__,flush=True)
        finally:
            SessionLocal.remove()
    output_predictions = [predictions[c['id']] for c in cases]
    (root/'repaired_predictions.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in output_predictions),encoding='utf-8')
    report = score(cases, output_predictions)
    semantic = ['correctness','faithfulness','relevance','citation_accuracy']
    for index, (case, row) in enumerate(zip(cases, report['cases']), 1):
        if row.get('error'):
            continue
        previous = old_scores.get(case['id'], {})
        if case['id'] not in replaced and previous.get('correctness') is not None and not previous.get('judge_error'):
            row.update({key: previous.get(key) for key in semantic})
            continue
        try:
            prediction = predictions[case['id']]
            row.update(judge_answer(case['question'],case['reference_answer'],prediction['answer'],prediction.get('context',[])))
        except Exception as error:
            row['judge_error'] = type(error).__name__
        print(f'Judge recovery {index}/{len(cases)}',flush=True)
    # Recompute semantic means using the recorded per-case scores, without extra API calls.
    for group in [report['overall'], *report['by_category'].values()]:
        group['correctness'] = None
    groups = [(report['overall'], report['cases'])] + [(summary,[r for r in report['cases'] if r['category']==category])
        for category,summary in report['by_category'].items()]
    for summary, rows in groups:
        for key in semantic:
            values = [r[key] for r in rows if isinstance(r.get(key),(int,float))]
            summary[key] = sum(values)/len(values) if values else None
            summary[key+'_count'] = len(values)
        summary['judge_error_count'] = sum(bool(r.get('judge_error')) for r in rows)
    report['metadata'] = {**old_report.get('metadata',{}), 'recovered_cases': sorted(replaced),
        'initial_error_rate': old_report['overall']['error_rate'], 'note': 'Original report and predictions preserved; only failed/missing cases were retried. Different workload from the initial concurrent run.'}
    (root/'repaired_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['overall']),flush=True)


if __name__ == '__main__':
    main()
