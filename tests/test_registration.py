import unittest
from unittest.mock import patch
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.models.Users import User
from src.routes.auth_routes import auth_bp


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        User.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.app = Flask(__name__)
        self.app.register_blueprint(auth_bp)
        self.client = self.app.test_client()
        self.sessions = patch('src.routes.auth_routes.SessionLocal', return_value=self.session)
        self.sessions.start()

    def tearDown(self):
        self.sessions.stop()
        self.session.close()
        self.engine.dispose()

    def test_registration_and_duplicate_status(self):
        payload = {'email': 'signup@example.com', 'password': 'example-password-123'}
        self.assertEqual(self.client.post('/api/register', json=payload).status_code, 201)
        duplicate = self.client.post('/api/register', json=payload)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json['code'], 'email_exists')

    def test_invalid_password_is_not_echoed(self):
        response = self.client.post('/api/register', json={'email': 'signup@example.com', 'password': 'x#z'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('x#z', response.get_data(as_text=True))

    def test_invalid_email_has_serializable_details(self):
        response = self.client.post('/api/register', json={'email': 'invalid', 'password': 'example-password-123'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['code'], 'invalid_input')

    def test_non_object_body(self):
        for body in [None, [], 'text']:
            self.assertEqual(self.client.post('/api/register', json=body).status_code, 400)

    def test_database_failure_is_not_reported_as_bad_credentials(self):
        with patch('src.services.user_service.User.get_by_emails', side_effect=RuntimeError('private database detail')):
            response = self.client.post('/api/register', json={'email': 'signup@example.com', 'password': 'example-password-123'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private database detail', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
