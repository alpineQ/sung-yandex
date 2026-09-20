import os
import sys
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).parents[1] / 'helper'))
import yandex
import yandex_credentials as credentials


class AccountTests(unittest.TestCase):
    def test_keyring_token_is_passed_only_on_stdin(self):
        with patch.dict(os.environ, {'SUNG_YANDEX_DISABLE_KEYRING': '0'}), patch.object(credentials.subprocess, 'run', return_value=Mock(returncode=0, stdout='')) as run:
            credentials.secret_tool('store', 'private-test-token')
        self.assertNotIn('private-test-token', ' '.join(run.call_args.args[0]))
        self.assertEqual(run.call_args.kwargs['input'], 'private-test-token')

    def test_invalid_token_never_replaces_saved_credential(self):
        with patch.object(yandex, 'Api') as api, patch.object(credentials, 'secret_tool') as keyring:
            api.return_value.get.side_effect = ValueError('Denied')
            with self.assertRaises(ValueError): credentials.connect({'token': 'invalid', 'remember': True})
            keyring.assert_not_called()

    def test_session_connection_does_not_write_keyring(self):
        with patch.object(yandex, 'Api') as api, patch.object(credentials, 'secret_tool') as keyring:
            api.return_value.get.return_value = {'account': {'uid': 1, 'displayName': 'Test'}}
            result = credentials.connect({'token': 'valid', 'remember': False})
            self.assertEqual(result['uid'], '1')
            keyring.assert_not_called()

    def test_keyring_failure_is_visible_without_plaintext_fallback(self):
        with patch.dict(os.environ, {'SUNG_YANDEX_DISABLE_KEYRING': '0'}), patch.object(credentials.subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, 'keyring'):
                credentials.secret_tool('store', 'token')

    def test_artist_pages_have_no_first_hundred_limit(self):
        with patch.object(yandex, 'Api') as api:
            api.return_value.get.side_effect = [
                {'tracks': [{'id': n} for n in range(100)], 'pager': {'total': 101}},
                {'artist': {'name': 'Artist'}},
                {'tracks': [{'id': 100}], 'pager': {'total': 101}},
            ]
            first = yandex.run({'op': 'artist', 'id': 'ym:5'})
            second = yandex.run({'op': 'artist', 'id': 'ym:5', 'page': first['nextPage']})
            self.assertTrue(first['hasMore'])
            self.assertFalse(second['hasMore'])
            self.assertEqual(len(first['items'] + second['items']), 101)
            self.assertEqual(api.return_value.get.call_args.args[1]['page'], 1)

if __name__ == '__main__': unittest.main()
