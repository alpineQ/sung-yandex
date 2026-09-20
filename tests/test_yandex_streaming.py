import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).parents[1] / 'helper'))
import yandex
import yandex_cache as cache
import yandex_wave as wave


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'YANDEX_MUSIC_CACHE_DIR': self.temp.name,
                              'YANDEX_MUSIC_TOKEN': '', 'YANDEX_MUSIC_ENV_FILE': '', 'SUNG_YANDEX_DISABLE_KEYRING': '1'})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_resolve_returns_before_downloading_audio(self):
        with patch.object(yandex, 'Api') as api, patch.object(yandex, 'urlopen', side_effect=AssertionError('download attempted')):
            api.return_value.file_info.return_value = {'codec': 'flac-mp4', 'url': 'https://cdn.example/audio'}
            result = yandex.run({'op': 'resolve', 'id': 'ym:42'})
            self.assertEqual(result['url'], 'https://cdn.example/audio')
            self.assertTrue(result['download'])
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_lyrics_survive_restart_without_credentials_or_network(self):
        cache.atomic_write(cache.lyric_path('42'), b'[00:01.00] Offline lyric')
        with patch.object(yandex, 'Api', side_effect=AssertionError('API attempted')):
            result = yandex.run({'op': 'lyrics', 'id': 'ym:42'})
        self.assertIn('Offline lyric', result['lrc'])

    def test_cached_cover_is_used_by_catalog_and_cached_tracks(self):
        url = 'https://example.com/400x400'
        cache.atomic_write(cache.artwork_path(url), b'image-fixture')
        self.assertEqual(yandex.cover({'coverUri': 'example.com/%%'}), cache.artwork_path(url).as_uri())

    def test_wave_uses_sessions_and_keeps_feedback(self):
        result = {'radioSessionId': 'session-1', 'batchId': 'batch-1', 'wave': {'idForFrom': 'wave'},
                  'sequence': [{'track': {'id': '42', 'title': 'Track'}}, {'track': {'id': '43', 'available': False}}]}
        with patch.object(yandex, 'Api') as api:
            api.return_value.get.return_value = result
            first = wave.run({'op': 'wave-start'})
            self.assertEqual(api.return_value.get.call_args.args[0], 'rotor/session/new')
            self.assertEqual(len(first['items']), 1)
            self.assertEqual(first['items'][0]['_waveBatch'], 'batch-1')
            feedback = [{'batch_id': 'batch-1', 'event': {'type': 'skip', 'trackId': '42'}}]
            wave.run({'op': 'wave-next', 'session': first['session'], 'queue': ['42'], 'feedbacks': feedback})
            self.assertEqual(api.return_value.get.call_args.kwargs['json_data']['feedbacks'], feedback)

    def test_quota_evicts_oldest_and_preserves_active_track(self):
        root = Path(self.temp.name)
        for identity, age in [('1', 1), ('2', 2), ('3', 3)]:
            path = root / f'{identity}.mp3'
            path.write_bytes(b'x' * 10)
            os.utime(path, (age, age))
            (root / f'{identity}.meta.json').write_text('{}')
            cache.atomic_write(cache.lyric_path(identity), b'lyrics')
        (root / '4.mp3.tmp').write_bytes(b'incomplete')
        result = cache.prune(20, protected=('1',))
        self.assertEqual(result['removed'], 1)
        self.assertTrue((root / '1.mp3').exists())
        self.assertFalse((root / '2.mp3').exists())
        self.assertFalse((root / '2.meta.json').exists())
        self.assertFalse(cache.lyric_path('2').exists())
        self.assertTrue((root / '4.mp3.tmp').exists())

    def test_saved_token_precedes_automatic_dotenv_and_logout_blocks_both(self):
        envfile = Path(self.temp.name) / '.env'
        envfile.write_text('YANDEX_MUSIC_TOKEN=fixture-fallback')
        with patch.dict(os.environ, {'YANDEX_MUSIC_FALLBACK_ENV_FILE': str(envfile), 'SUNG_YANDEX_LOGGED_OUT': ''}), patch('yandex_credentials.load', return_value='fixture-keyring'):
            self.assertEqual(yandex.token(), 'fixture-keyring')
            with patch.dict(os.environ, {'SUNG_YANDEX_LOGGED_OUT': '1'}):
                self.assertEqual(yandex.token(), '')

    def test_expired_wave_session_starts_a_new_session(self):
        with patch.object(yandex, 'Api') as api:
            api.return_value.get.side_effect = [{'unknownSession': True}, {'radioSessionId': 'new', 'sequence': []}]
            result = wave.run({'op': 'wave-next', 'session': 'old'})
            self.assertEqual(result['session'], 'new')
            self.assertEqual(api.return_value.get.call_args.args[0], 'rotor/session/new')

if __name__ == '__main__': unittest.main()
