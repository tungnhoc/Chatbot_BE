"""Apply the v1 upgrade to an existing MySQL schema. Does not run on app startup."""
from pathlib import Path
import re
from sqlalchemy import inspect, text
from src.config.db_session import engine


def user_table_sql(statement):
    """Adapt historical SQL table identifiers without rewriting migration files."""
    statement = re.sub(r'\bALTER TABLE Users\b', 'ALTER TABLE users', statement)
    return re.sub(r'\bREFERENCES Users(?=\s*\()', 'REFERENCES users', statement)


def main():
    if engine.dialect.name != 'mysql':
        raise RuntimeError('Upgrade requires MySQL')
    inspector = inspect(engine)
    if not inspector.has_table('users'):
        raise RuntimeError('Initialize base tables from mysql.sql first')
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '001_multiformat.sql'
    statements = [part.strip() for part in '\n'.join(
        line for line in migration.read_text(encoding='utf-8').splitlines()
        if not line.lstrip().startswith('--')).split(';') if part.strip()]
    has_role = 'Role' in {column['name'] for column in inspector.get_columns('users')}
    with engine.begin() as connection:
        for statement in statements:
            statement = user_table_sql(statement)
            if statement.startswith('ALTER TABLE users') and has_role:
                continue
            connection.execute(text(statement))
    inspector = inspect(engine)
    if 'AssistantMessageID' not in {column['name'] for column in inspector.get_columns('ChatTraces')}:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE ChatTraces ADD COLUMN AssistantMessageID INT NULL UNIQUE'))
    uniques = inspector.get_unique_constraints('ConversationDocuments')
    primary = inspector.get_pk_constraint('ConversationDocuments').get('constrained_columns', [])
    if set(primary) != {'ConversationID', 'DocumentID'} and not any(
        set(u['column_names']) == {'ConversationID', 'DocumentID'} for u in uniques
    ):
        # Existing duplicates need manual resolution rather than deletion.
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE ConversationDocuments ADD UNIQUE KEY uq_conversation_document (ConversationID,DocumentID)'))
    print('Multiformat v1 migration applied. Existing originals must be re-uploaded to the new pipeline.')


if __name__ == '__main__':
    main()
