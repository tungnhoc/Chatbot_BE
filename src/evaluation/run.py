"""Score JSONL traces against a labeled dataset; optionally replay through the chat service."""
import argparse
import csv
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from src.evaluation.metrics import retrieval_metrics, citation_metrics, judge_answer, percentile, numeric_fact_match


def read_jsonl(path):
    with open(path, encoding='utf-8-sig') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def replay(dataset, output, user_id):
    from src.config.db_session import SessionLocal
    from src.services.chat_service import handle_chat_query
    from sqlalchemy import text
    with open(output, 'w', encoding='utf-8') as handle:
        for case in dataset:
            session = SessionLocal()
            try:
                result = handle_chat_query(session, str(user_id), case['question'],
                    conversation_id=case['conversation_id'], document_ids=case.get('document_ids'))
                value = session.execute(text('SELECT Payload FROM ChatTraces WHERE TraceID=:id AND UserID=:uid'),
                                        {'id': result['trace_id'], 'uid': user_id}).scalar_one()
                trace = json.loads(value) if isinstance(value, str) else value
                handle.write(json.dumps({'id': case['id'], **trace}, ensure_ascii=False) + '\n')
            except Exception as exc:
                session.rollback()
                handle.write(json.dumps({'id': case['id'], 'error': type(exc).__name__}) + '\n')
            finally:
                SessionLocal.remove()


def score(dataset, predictions, use_judge=False, k=8):
    by_id = {p['id']: p for p in predictions}
    if len(by_id) != len(predictions):
        raise ValueError('Duplicate prediction IDs')
    if len({c['id'] for c in dataset}) != len(dataset):
        raise ValueError('Duplicate dataset IDs')
    rows = []
    for case in dataset:
        prediction = by_id.get(case['id'])
        row = {'id': case['id'], 'category': case.get('category', 'unspecified')}
        if not prediction or prediction.get('error'):
            rows.append({**row, 'error': prediction.get('error') if prediction else 'missing_prediction'})
            continue
        if prediction.get('query') != case['question']:
            raise ValueError('Question mismatch for case ' + str(case['id']))
        row.update(retrieval_metrics(prediction.get('retrieved', []), case.get('relevant_sources', []), k))
        row.update(citation_metrics(prediction['answer'], prediction.get('sources', [])))
        row['latency_ms'] = prediction.get('latency_ms')
        if case.get('expected_values'):
            row['numeric_fact_match'] = numeric_fact_match(prediction['answer'], case['expected_values'])
        if use_judge:
            try:
                row.update(judge_answer(case['question'], case['reference_answer'],
                                        prediction['answer'], prediction.get('context', [])))
            except Exception as exc:
                row['judge_error'] = type(exc).__name__
        rows.append(row)
    def aggregate(group):
        result = {'count': len(group), 'error_rate': sum(bool(r.get('error')) for r in group) / len(group) if group else None}
        for key in ('precision_at_k', 'recall_at_k', 'citation_id_validity', 'numeric_fact_match', 'correctness', 'faithfulness', 'relevance', 'citation_accuracy'):
            values = [r[key] for r in group if isinstance(r.get(key), (int, float))]
            result[key] = sum(values) / len(values) if values else None
            result[key + '_count'] = len(values)
        latencies = [r['latency_ms'] for r in group if isinstance(r.get('latency_ms'), (int, float))]
        result.update(latency_p50_ms=percentile(latencies, .5), latency_p95_ms=percentile(latencies, .95))
        result['judge_error_count'] = sum('judge_error' in r for r in group)
        return result
    return {'overall': aggregate(rows), 'by_category': {
        category: aggregate([r for r in rows if r['category'] == category])
        for category in sorted({r['category'] for r in rows})}, 'cases': rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--output', default='evaluation-results/report')
    parser.add_argument('--judge', action='store_true', help='Calls Groq; incurs API usage and sends evaluation content')
    parser.add_argument('--replay-user', type=int, help='Run live chat for dataset conversations as this owner; writes messages/traces')
    parser.add_argument('--k', type=int, default=8)
    args = parser.parse_args()
    if args.k < 1:
        parser.error('--k must be positive')
    dataset = read_jsonl(args.dataset)
    if args.replay_user is not None:
        replay(dataset, args.predictions, args.replay_user)
    report = score(dataset, read_jsonl(args.predictions), args.judge, args.k)
    report['metadata'] = {'created_at': datetime.now(timezone.utc).isoformat(), 'k': args.k,
        'judge_enabled': args.judge, 'judge_model': os.getenv('GROQ_MODEL') if args.judge else None,
        'evaluator_version': 'v1', 'dataset': args.dataset}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = sorted({key for row in report['cases'] for key in row})
    with output.with_suffix('.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report['cases'])
    print(json.dumps(report['overall'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
