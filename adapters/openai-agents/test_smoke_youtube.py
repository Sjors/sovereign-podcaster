"""Offline transport regressions; no credentials or API calls required."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error


spec = importlib.util.spec_from_file_location('smoke_youtube', Path(__file__).with_name('smoke-youtube.py'))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class APIResponseTests(unittest.TestCase):
    def call_with(self, status, payload):
        response = io.BytesIO(payload)
        response.status = status
        api = smoke.API('synthetic-test-credential', 'synthetic-project')
        with patch.object(api, 'open', return_value=response):
            return api.call('sessions/synthetic/events', {'events': []})

    def test_empty_accepted_event_does_not_fail_or_cancel_task(self):
        self.assertIsNone(self.call_with(202, b''))

    def test_empty_no_content_acknowledgement(self):
        self.assertIsNone(self.call_with(204, b''))

    def test_json_session_response(self):
        self.assertEqual(self.call_with(200, b'{"id":"synthetic"}'), {'id': 'synthetic'})

    def test_missing_json_resource_response_is_still_an_error(self):
        with self.assertRaises(json.JSONDecodeError):
            self.call_with(200, b'')

    def test_permission_error_keeps_request_id_and_redacts_credential(self):
        api = smoke.API('synthetic-test-credential', 'synthetic-project')
        body = json.dumps({'error': {'code': 'unauthorized', 'message':
            'Missing api.responses.write for synthetic-test-credential'}}).encode()
        error = urllib.error.HTTPError('https://api.openai.com/synthetic', 401,
            'Unauthorized', {'x-request-id': 'req_synthetic'}, io.BytesIO(body))
        with patch.object(api.opener, 'open', side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                api.call('sessions/synthetic/events', {'events': []})
        self.assertIn('req_synthetic', str(caught.exception))
        self.assertIn('api.responses.write', str(caught.exception))
        self.assertNotIn('synthetic-test-credential', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
