import runpy
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests
from src.workers import ingestion


class IngestionRuntimeTests(unittest.TestCase):
    def test_embedded_worker_starts_once_and_stops(self):
        thread = MagicMock()
        thread.is_alive.return_value = True
        with patch.dict('os.environ', {'INGESTION_WORKER_MODE': 'embedded'}), patch.object(ingestion, '_thread', None), patch.object(ingestion, '_stop', None), patch.object(ingestion, 'Thread', return_value=thread) as factory:
            self.assertIs(ingestion.start_worker_thread(), thread)
            self.assertIs(ingestion.start_worker_thread(), thread)
            factory.assert_called_once()
            thread.start.assert_called_once()
            stop = factory.call_args.kwargs['args'][0]
            self.assertFalse(stop.is_set())
            ingestion.stop_worker_thread()
            self.assertTrue(stop.is_set())
            thread.join.assert_called_once_with(timeout=3)

    def test_external_mode_does_not_start_embedded_thread(self):
        with patch.dict('os.environ', {'INGESTION_WORKER_MODE': 'external'}), patch.object(ingestion, 'Thread') as thread:
            self.assertIsNone(ingestion.start_worker_thread())
            thread.assert_not_called()

    def test_invalid_worker_mode_fails_clearly(self):
        with patch.dict('os.environ', {'INGESTION_WORKER_MODE': 'incorrect'}):
            with self.assertRaises(ValueError):
                ingestion.start_worker_thread()

    def test_idle_loop_is_interruptible(self):
        stop = MagicMock()
        stop.is_set.side_effect = [False, True]
        with patch.object(ingestion, 'run_once', return_value=False) as run_once:
            ingestion.run_forever(stop)
        run_once.assert_called_once()
        stop.wait.assert_called_once_with(2)

    def test_gunicorn_hooks_start_worker_after_fork(self):
        with patch.object(ingestion, 'start_worker_thread') as start, patch.object(ingestion, 'stop_worker_thread') as stop:
            hooks = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'gunicorn.conf.py'))
            start.assert_not_called()
            hooks['post_worker_init'](MagicMock())
            start.assert_called_once()
            hooks['worker_exit'](MagicMock(), MagicMock())
            stop.assert_called_once()

    def test_credit_errors_are_actionable_without_provider_payload(self):
        response = requests.Response()
        response.status_code = 402
        message, permanent = ingestion.processing_failure(requests.HTTPError('private provider payload', response=response))
        self.assertTrue(permanent)
        self.assertTrue(message.startswith('embedding_credits:'))
        self.assertNotIn('private', message)

    def test_transient_provider_errors_can_retry(self):
        for status in [429, 500, 503]:
            response = requests.Response()
            response.status_code = status
            message, permanent = ingestion.processing_failure(requests.HTTPError(response=response))
            self.assertFalse(permanent)

    def test_missing_original_does_not_leak_storage_path(self):
        message, permanent = ingestion.processing_failure(FileNotFoundError('/private/path.pdf'))
        self.assertTrue(permanent)
        self.assertTrue(message.startswith('source_file_missing:'))
        self.assertNotIn('/private', message)

    def test_browser_can_preflight_direct_upload_with_bearer_auth(self):
        from src.app import app
        response = app.test_client().options('/api/conversations/1/documents', headers={
            'Origin': 'https://chatbot-fe-peach-omega.vercel.app',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'],
                         'https://chatbot-fe-peach-omega.vercel.app')
        self.assertIn('authorization', response.headers['Access-Control-Allow-Headers'].lower())


if __name__ == '__main__':
    unittest.main()
