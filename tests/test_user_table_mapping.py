"""Case-sensitive MySQL SQL/mapping regression checks; no live database required."""
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import AddConstraint

from src.config.base import Base
from src.models.Users import User
from src.models.Conversations import Conversations
from src.models.Documents import Documents
from src.models.DocumentChunks import DocumentChunks
from src.models.Messages import Messages
from src.models.TokenBlacklist import TokenBlacklist
from src.models.VectorMemorySummary import VectorMemorySummary
from src.config import migrate


class UserTableMappingTests(unittest.TestCase):
    def test_mysql_query_targets_existing_lowercase_table(self):
        statement = select(User).where(User.Email == 'mapping@example.com')
        sql = str(statement.compile(dialect=mysql.dialect()))
        self.assertIn('FROM users', sql)
        self.assertNotIn('FROM `Users`', sql)
        self.assertNotIn('FROM Users', sql)

    def test_all_foreign_keys_resolve_without_changing_other_table_names(self):
        configure_mappers()
        self.assertEqual(set(Base.metadata.tables), {
            'users', 'Conversations', 'Documents', 'DocumentChunks',
            'Messages', 'TokenBlacklist', 'VectorMemorySummary'})
        # Sorting resolves dependencies, including indirect references through conversations/documents.
        ordered = [table.name for table in Base.metadata.sorted_tables]
        self.assertLess(ordered.index('users'), ordered.index('Conversations'))
        self.assertLess(ordered.index('users'), ordered.index('Documents'))
        for table in Base.metadata.tables.values():
            for foreign_key in table.foreign_keys:
                self.assertIsNotNone(foreign_key.column)
                self.assertFalse(foreign_key.target_fullname.startswith('Users.'))
        for model, column, ondelete in [(Conversations, 'UserID', 'CASCADE'),
                                        (Documents, 'UploadedBy', 'SET NULL')]:
            foreign_key = next(iter(model.__table__.c[column].foreign_keys))
            self.assertIs(foreign_key.column, User.__table__.c.UserID)
            self.assertEqual(foreign_key.ondelete, ondelete)
            ddl = str(AddConstraint(foreign_key.constraint).compile(dialect=mysql.dialect()))
            self.assertIn('REFERENCES users', ddl)

    def test_historical_sql_adaptation_changes_only_table_identifiers(self):
        statement = ('ALTER TABLE Users ADD COLUMN Role VARCHAR(20); '
                     'CONSTRAINT FK_Documents_Users FOREIGN KEY (UploadedBy) REFERENCES Users(UserID)')
        result = migrate.user_table_sql(statement)
        self.assertIn('ALTER TABLE users ADD COLUMN Role', result)
        self.assertIn('REFERENCES users(UserID)', result)
        self.assertIn('FK_Documents_Users', result)
        unchanged = 'SELECT Users FROM Documents; SELECT * FROM Conversations'
        self.assertEqual(migrate.user_table_sql(unchanged), unchanged)

    def test_runner_accepts_case_sensitive_lowercase_schema(self):
        inspector = MagicMock()
        inspector.has_table.side_effect = lambda name: name == 'users'
        inspector.get_columns.side_effect = lambda name: (
            [{'name': 'Role'}] if name == 'users' else [{'name': 'AssistantMessageID'}])
        inspector.get_pk_constraint.return_value = {'constrained_columns': ['ConversationID', 'DocumentID']}
        inspector.get_unique_constraints.return_value = []
        engine = MagicMock()
        engine.dialect.name = 'mysql'
        with patch.object(migrate, 'engine', engine), patch.object(migrate, 'inspect', return_value=inspector), patch('builtins.print'):
            migrate.main()
        inspector.has_table.assert_called_once_with('users')
        inspector.get_columns.assert_any_call('users')
        connection = engine.begin.return_value.__enter__.return_value
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertTrue(any('REFERENCES users(UserID)' in sql for sql in statements))
        self.assertFalse(any('REFERENCES Users(' in sql or 'ALTER TABLE Users' in sql for sql in statements))
        self.assertFalse(any('RENAME TABLE' in sql or 'DROP TABLE' in sql for sql in statements))
        engine.connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
