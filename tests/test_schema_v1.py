import re
import sqlite3
import unittest
from unittest.mock import MagicMock

from src.config.schema_v1 import audit, plan, REQUIRED_COLUMNS, PRIMARY_KEYS, UNIQUES, FOREIGN_KEYS


def inspector_for_complete_schema():
    inspector = MagicMock()
    inspector.get_table_names.return_value = list(REQUIRED_COLUMNS)
    inspector.get_columns.side_effect = lambda name: [{'name': value} for value in REQUIRED_COLUMNS[name].split()]
    inspector.get_pk_constraint.side_effect = lambda name: {'constrained_columns': list(PRIMARY_KEYS[name])}
    inspector.get_unique_constraints.side_effect = lambda name: [
        {'column_names': list(columns)} for columns in UNIQUES.get(name, [])]
    inspector.get_foreign_keys.side_effect = lambda name: [
        {'constrained_columns': [column], 'referred_table': parent, 'referred_columns': [parent_column],
         'options': {'ondelete': action}} for column, parent, parent_column, action in FOREIGN_KEYS.get(name, [])]
    inspector.get_indexes.return_value = [{'column_names': ['Status', 'NextAttemptAt']}]
    return inspector


class SchemaAuditTests(unittest.TestCase):
    def test_complete_schema_is_noop(self):
        self.assertEqual(audit(inspector_for_complete_schema()), [])
        self.assertEqual(plan([]), [])

    def test_baseline_missing_supplemental_tables(self):
        inspector = inspector_for_complete_schema()
        inspector.get_table_names.return_value = [t for t in REQUIRED_COLUMNS
            if t not in {'ConversationDocuments', 'IngestionJobs', 'ChatTraces'}]
        issues = audit(inspector)
        self.assertEqual({i['table'] for i in issues}, {'ConversationDocuments', 'IngestionJobs', 'ChatTraces'})
        statements = plan(issues)
        self.assertEqual(len(statements), 3)
        self.assertIn('REFERENCES users(UserID)', statements[1])
        self.assertIn('ix_job_queue (Status, NextAttemptAt)', statements[1])
        self.assertIn('AssistantMessageID INT NULL UNIQUE', statements[2])

    def test_case_mismatch_does_not_create_duplicate_table(self):
        inspector = inspector_for_complete_schema()
        inspector.get_table_names.return_value = [t if t != 'ConversationDocuments' else 'conversationdocuments'
                                                 for t in REQUIRED_COLUMNS]
        issues = audit(inspector)
        self.assertEqual(issues[0]['kind'], 'wrong_case')
        with self.assertRaisesRegex(RuntimeError, 'no changes made'):
            plan(issues)

    def test_missing_queue_index_and_foreign_key_are_reported(self):
        inspector = inspector_for_complete_schema()
        inspector.get_indexes.return_value = []
        original = inspector.get_foreign_keys.side_effect
        inspector.get_foreign_keys.side_effect = lambda name: [] if name == 'IngestionJobs' else original(name)
        issues = audit(inspector)
        self.assertTrue(any(i['kind'] == 'missing_queue_index' for i in issues))
        self.assertEqual(sum(i['kind'] == 'foreign_key_mismatch' for i in issues), 2)
        with self.assertRaises(RuntimeError):
            plan(issues)

    def test_existing_trace_table_adds_only_known_nullable_column(self):
        statements = plan([{'table': 'ChatTraces', 'kind': 'missing_column', 'column': 'AssistantMessageID'},
                           {'table': 'ChatTraces', 'kind': 'missing_unique', 'columns': ['AssistantMessageID']}])
        self.assertEqual(statements, ['ALTER TABLE ChatTraces ADD COLUMN AssistantMessageID INT NULL UNIQUE'])

    def test_missing_base_tables_block_all_changes(self):
        with self.assertRaises(RuntimeError):
            plan([{'table': 'users', 'kind': 'missing_table'},
                  {'table': 'ConversationDocuments', 'kind': 'missing_table'}])

    def test_sql_constraints_and_defaults_on_local_sqlite(self):
        # MySQL-only named KEY syntax is translated for this local constraint test.
        # MySQL DDL itself is not claimed to have been executed here.
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('PRAGMA foreign_keys=ON')
        for table, column in [('users','UserID'), ('Documents','DocumentID'), ('Conversations','ConversationID')]:
            db.execute(f'CREATE TABLE {table} ({column} INTEGER PRIMARY KEY)')
            db.execute(f'INSERT INTO {table} VALUES (1)')
        for statement in plan([{'table': name, 'kind': 'missing_table'}
                               for name in ['ConversationDocuments','IngestionJobs','ChatTraces']]):
            statement = re.sub(r'UNIQUE KEY \w+', 'UNIQUE', statement)
            statement = re.sub(r'\s*KEY ix_job_queue \(Status, NextAttemptAt\),', '', statement)
            db.execute(statement)
        db.execute('INSERT INTO ConversationDocuments (ConversationID,DocumentID) VALUES (1,1)')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('INSERT INTO ConversationDocuments (ConversationID,DocumentID) VALUES (1,1)')
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('INSERT INTO ConversationDocuments (ConversationID,DocumentID) VALUES (1,99)')
        db.execute("INSERT INTO IngestionJobs (JobID,DocumentID,UserID,ContentHash,PipelineVersion) VALUES ('job',1,1,'hash','v1')")
        self.assertEqual(db.execute('SELECT Status,Attempts FROM IngestionJobs').fetchone(), ('queued',0))


if __name__ == '__main__':
    unittest.main()
