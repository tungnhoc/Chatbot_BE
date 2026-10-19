"""Read-only schema audit by default; explicit --apply adds known missing v1 schema."""
import argparse
import json
import re
from pathlib import Path
from sqlalchemy import inspect, text

# ORM models + live handwritten SQL. Extra legacy columns are allowed.
REQUIRED_COLUMNS = {
    'users': 'UserID UserName Email PasswordHash CreatedAt Role',
    'Documents': 'DocumentID FileName FilePath FileType UploadedBy UploadedAt FileSizeMB Description',
    'DocumentChunks': 'ChunkID DocumentID ChunkText Embedding Metadata CreatedAt',
    'Conversations': 'ConversationID UserID Title Summary CreatedAt UpdatedAt',
    'Messages': 'MessageID ConversationID Role Text Timestamp',
    'VectorMemorySummary': 'SummaryID ConversationID SummaryText Embedding CreatedAt',
    'TokenBlacklist': 'id jti created_at',
    'ConversationDocuments': 'ConversationID DocumentID FileURL UploadedAt IsDeleted',
    'IngestionJobs': 'JobID DocumentID UserID ContentHash PipelineVersion Status Attempts Error NextAttemptAt CreatedAt UpdatedAt',
    'ChatTraces': 'TraceID UserID ConversationID Payload CreatedAt AssistantMessageID',
}
PRIMARY_KEYS = {
    'users': ('UserID',), 'Documents': ('DocumentID',), 'DocumentChunks': ('ChunkID',),
    'Conversations': ('ConversationID',), 'Messages': ('MessageID',),
    'VectorMemorySummary': ('SummaryID',), 'TokenBlacklist': ('id',),
    'ConversationDocuments': ('ConversationID', 'DocumentID'),
    'IngestionJobs': ('JobID',), 'ChatTraces': ('TraceID',),
}
UNIQUES = {
    'users': [('Email',)], 'TokenBlacklist': [('jti',)],
    'IngestionJobs': [('DocumentID',), ('UserID', 'ContentHash', 'PipelineVersion')],
    'ChatTraces': [('AssistantMessageID',)],
}
FOREIGN_KEYS = {
    'Documents': [('UploadedBy', 'users', 'UserID', 'SET NULL')],
    'DocumentChunks': [('DocumentID', 'Documents', 'DocumentID', 'CASCADE')],
    'Conversations': [('UserID', 'users', 'UserID', 'CASCADE')],
    'Messages': [('ConversationID', 'Conversations', 'ConversationID', 'CASCADE')],
    'VectorMemorySummary': [('ConversationID', 'Conversations', 'ConversationID', 'CASCADE')],
    'ConversationDocuments': [('ConversationID', 'Conversations', 'ConversationID', 'CASCADE'),
                              ('DocumentID', 'Documents', 'DocumentID', 'CASCADE')],
    'IngestionJobs': [('DocumentID', 'Documents', 'DocumentID', 'CASCADE'),
                      ('UserID', 'users', 'UserID', 'CASCADE')],
    # Historical schema has no UserID or AssistantMessageID FK here; do not invent one.
    'ChatTraces': [('ConversationID', 'Conversations', 'ConversationID', 'CASCADE')],
}
SUPPLEMENTAL = {'ConversationDocuments', 'IngestionJobs', 'ChatTraces'}


def audit(inspector, case_sensitive=True):
    issues = []
    names = inspector.get_table_names()
    normalize = (lambda name: name) if case_sensitive else (lambda name: name.lower())
    available = {normalize(name): name for name in names}
    for table, required in REQUIRED_COLUMNS.items():
        actual = available.get(normalize(table))
        if actual is None:
            variant = next((name for name in names if name.lower() == table.lower()), None)
            issues.append({'table': table, 'kind': 'wrong_case' if variant else 'missing_table', 'actual': variant})
            continue
        columns = {column['name'] for column in inspector.get_columns(actual)}
        for column in required.split():
            if column not in columns:
                issues.append({'table': table, 'kind': 'missing_column', 'column': column})
        primary = tuple(inspector.get_pk_constraint(actual).get('constrained_columns') or [])
        unique_sets = [set(item['column_names']) for item in inspector.get_unique_constraints(actual)] + [set(primary)]
        # Legacy ConversationDocuments may have an ID PK plus a composite UNIQUE.
        if table == 'ConversationDocuments':
            if set(PRIMARY_KEYS[table]) not in unique_sets:
                issues.append({'table': table, 'kind': 'missing_unique', 'columns': list(PRIMARY_KEYS[table])})
        elif primary != PRIMARY_KEYS[table]:
            issues.append({'table': table, 'kind': 'primary_key_mismatch'})
        for unique in UNIQUES.get(table, []):
            if set(unique) not in unique_sets:
                issues.append({'table': table, 'kind': 'missing_unique', 'columns': list(unique)})
        foreign_keys = inspector.get_foreign_keys(actual)
        for column, parent, parent_column, ondelete in FOREIGN_KEYS.get(table, []):
            if not any(fk['constrained_columns'] == [column]
                       and normalize(fk['referred_table']) == normalize(parent)
                       and fk['referred_columns'] == [parent_column]
                       and (fk.get('options', {}).get('ondelete') or '').upper() == ondelete
                       for fk in foreign_keys):
                issues.append({'table': table, 'kind': 'foreign_key_mismatch', 'column': column,
                               'expected': f'{parent}.{parent_column} ON DELETE {ondelete}'})
        if table == 'IngestionJobs':
            if not any(tuple(index['column_names'][:2]) == ('Status', 'NextAttemptAt')
                       for index in inspector.get_indexes(actual)):
                issues.append({'table': table, 'kind': 'missing_queue_index'})
    return issues


def plan(issues):
    """Never infer a repair for an incompatible populated table."""
    blocked = []
    for issue in issues:
        allowed = issue['kind'] == 'missing_table' and issue['table'] in SUPPLEMENTAL
        allowed |= issue['kind'] == 'missing_column' and (issue['table'], issue.get('column')) in {
            ('users', 'Role'), ('ChatTraces', 'AssistantMessageID')}
        allowed |= (issue['table'] == 'ChatTraces' and issue['kind'] == 'missing_unique'
                    and issue.get('columns') == ['AssistantMessageID']
                    and any(i['table'] == 'ChatTraces' and i['kind'] == 'missing_column'
                            and i.get('column') == 'AssistantMessageID' for i in issues))
        if not allowed:
            blocked.append(issue)
    if blocked:
        raise RuntimeError('Schema differs from known definitions; no changes made: ' + json.dumps(blocked))
    sql_path = Path(__file__).resolve().parents[2] / 'migrations/002_runtime_tables.sql'
    sql = '\n'.join(line for line in sql_path.read_text(encoding='utf-8').splitlines()
                    if not line.lstrip().startswith('--'))
    statements = []
    missing = {i['table'] for i in issues if i['kind'] == 'missing_table'}
    for statement in sql.split(';'):
        if not statement.strip():
            continue
        table = re.match(r'CREATE TABLE IF NOT EXISTS (\w+)', statement.strip()).group(1)
        if table in missing:
            statements.append(statement.strip())
    if any(i['table'] == 'users' and i.get('column') == 'Role' for i in issues):
        statements.insert(0, "ALTER TABLE users ADD COLUMN Role VARCHAR(20) NOT NULL DEFAULT 'user'")
    if any(i['table'] == 'ChatTraces' and i.get('column') == 'AssistantMessageID' for i in issues):
        statements.append('ALTER TABLE ChatTraces ADD COLUMN AssistantMessageID INT NULL UNIQUE')
    return statements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Read-only audit (default)')
    mode.add_argument('--apply', action='store_true', help='Explicitly apply missing supplemental schema')
    args = parser.parse_args()
    from src.config.database import get_database_engine
    engine = get_database_engine()
    if engine.dialect.name != 'mysql':
        raise RuntimeError('Requires MySQL')
    with engine.connect() as connection:
        case_sensitive = connection.execute(text('SELECT @@lower_case_table_names')).scalar_one() == 0
        issues = audit(inspect(connection), case_sensitive)
    if args.apply:
        statements = plan(issues)
        if statements:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
        with engine.connect() as connection:
            issues = audit(inspect(connection), case_sensitive)
    print(json.dumps({'schema_ready': not issues, 'issues': issues}, indent=2))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
