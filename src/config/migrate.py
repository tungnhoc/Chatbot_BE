"""Apply the v1 upgrade to an existing MySQL schema. Does not run on app startup."""
from pathlib import Path
from sqlalchemy import inspect, text
from src.config.db_session import engine


def main():
    if engine.dialect.name != 'mysql':
        raise RuntimeError('Upgrade requires MySQL')
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if 'Users' not in tables and 'users' not in tables:
        raise RuntimeError('Initialize base tables from mysql.sql first')
    # Do not silently rename a live case-sensitive deployment.
    with engine.connect() as connection:
        case_mode = connection.execute(text('SELECT @@lower_case_table_names')).scalar_one()
    if 'Users' not in tables and 'users' in tables and case_mode == 0:
        raise RuntimeError('Normalize the existing users table to Users before migrating')
    migration = Path(__file__).resolve().parents[2] / 'migrations' / '001_multiformat.sql'
    statements = [part.strip() for part in '\n'.join(
        line for line in migration.read_text(encoding='utf-8').splitlines()
        if not line.lstrip().startswith('--')).split(';') if part.strip()]
    user_table = 'Users' if 'Users' in tables else 'users'
    has_role = 'Role' in {column['name'] for column in inspector.get_columns(user_table)}
    with engine.begin() as connection:
        for statement in statements:
            if statement.startswith('ALTER TABLE Users') and has_role:
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
