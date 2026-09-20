import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).parents[1] / 'helper'))
import yandex
import yandex_library as library

RAW = {'kind': 7, 'owner': {'uid': 1}, 'title': 'Test', 'revision': 4,
       'tracks': [{'id': '42', 'track': {'id': '42', 'title': 'Song', 'albums': [{'id': 9}]}}]}
SONG = {'id': 'ym:42', 'albumId': 'ym:9'}


class LibraryTests(unittest.TestCase):
    def test_revision_conflict_does_not_write(self):
        with patch.object(yandex, 'Api') as cls:
            cls.return_value.get.side_effect = [{'account': {'uid': 1}}, RAW]
            with self.assertRaisesRegex(ValueError, 'another device'):
                library.run({'op': 'yandex-playlist-edit', 'id': 'ym:1:7', 'revision': 3, 'items': []})
            self.assertEqual(cls.return_value.get.call_count, 2)
            self.assertTrue(all(not call.kwargs.get('data') for call in cls.return_value.get.call_args_list))

    def test_foreign_playlist_cannot_be_modified(self):
        with patch.object(yandex, 'Api') as cls:
            cls.return_value.get.return_value = {'account': {'uid': 2}}
            with self.assertRaisesRegex(ValueError, 'own regular'):
                library.run({'op': 'yandex-playlist-delete', 'id': 'ym:1:7'})
            self.assertEqual(cls.return_value.get.call_count, 1)

    def test_reorder_is_one_revision_checked_transaction(self):
        with patch.object(yandex, 'Api') as cls:
            cls.return_value.get.side_effect = [{'account': {'uid': 1}}, RAW, {**RAW, 'revision': 5}]
            result = library.run({'op': 'yandex-playlist-edit', 'id': 'ym:1:7', 'revision': 4, 'items': [SONG]})
            data = cls.return_value.get.call_args.kwargs['data']
            self.assertEqual(data['revision'], 4)
            self.assertEqual(json.loads(data['diff']), [{'op': 'delete', 'from': 0, 'to': 1}, {'op': 'insert', 'at': 0, 'tracks': [{'id': '42', 'albumId': '9'}]}])
            self.assertEqual(result['playlist']['revision'], 5)

    def test_local_files_rejected_before_creating_remote_playlist(self):
        with patch.object(yandex, 'Api') as cls:
            with self.assertRaisesRegex(ValueError, 'Yandex Music tracks only'):
                library.run({'op': 'yandex-playlist-create', 'title': 'Mixed', 'items': [{'id': 'local_abc', 'localPath': '/music/test.mp3'}]})
            cls.return_value.get.assert_not_called()

    def test_like_failure_is_propagated(self):
        with patch.object(yandex, 'Api') as cls:
            cls.return_value.get.side_effect = [{'account': {'uid': 1}}, ValueError('offline')]
            with self.assertRaisesRegex(ValueError, 'offline'):
                library.run({'op': 'yandex-like', 'id': 'ym:42', 'liked': True})

    def test_mutation_summary_fetches_full_playlist(self):
        api = Mock()
        api.get.return_value = RAW
        result = library.playlist_data(api, {**RAW, 'tracks': [], 'trackCount': 1})
        api.get.assert_called_once_with('users/1/playlists/7')
        self.assertEqual(result['tracks'][0]['id'], 'ym:42')

    def test_partial_create_preserves_created_playlist(self):
        with patch.object(yandex, 'Api') as cls:
            cls.return_value.get.side_effect = [{'account': {'uid': 1}}, {**RAW, 'tracks': []}, ValueError('offline')]
            result = library.run({'op': 'yandex-playlist-create', 'title': 'New', 'items': [SONG]})
            self.assertEqual(result['playlist']['id'], 'ym:1:7')
            self.assertIn('not added', result['warning'])

if __name__ == '__main__': unittest.main()
