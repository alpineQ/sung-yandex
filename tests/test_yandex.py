"""Offline regression tests for the provider and yamusic cache boundary."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parents[1] / 'helper'))
import yandex

TRACK = {'id': '42', 'title': 'Song', 'durationMs': 123000,
         'artists': [{'id': 8, 'name': 'Artist'}],
         'albums': [{'id': 9, 'title': 'Album', 'coverUri': 'example.com/%%'}]}


class Download(io.BytesIO):
    def __init__(self, data=b'audio', expected='5'):
        super().__init__(data)
        self.headers = {'Content-Length': expected}

    def geturl(self):
        return 'https://cdn.example/audio'


class YandexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'YANDEX_MUSIC_CACHE_DIR': str(self.root / 'cache'),
                                         'YANDEX_MUSIC_TOKEN': '', 'YANDEX_MUSIC_ENV_FILE': '', 'SUNG_YANDEX_DISABLE_KEYRING': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        yandex.cache_dir().mkdir()

    def cache(self):
        audio = yandex.cache_dir() / '42.flac-mp4'
        audio.write_bytes(b'audio')
        yandex.save_meta('42', TRACK)
        return audio

    def test_offline_buffer_uses_existing_yamusic_cache_without_api(self):
        audio = self.cache()
        playback = self.root / 'playback'
        playback.mkdir()
        with patch.object(yandex, 'Api', side_effect=AssertionError('Network attempted')):
            result = yandex.run({'op': 'buffer', 'id': 'ym:42', 'directory': str(playback)})
        target = Path(result['file'])
        self.assertEqual(target.parent, playback)
        self.assertEqual(target.read_bytes(), b'audio')
        target.unlink()
        self.assertTrue(audio.exists())

    def test_offline_home_reads_yamusic_sidecars(self):
        self.cache()
        home = yandex.run({'op': 'home'})
        song = home['sections'][0]['items'][0]
        self.assertEqual(song['id'], 'ym:42')
        self.assertEqual(song['title'], 'Song')
        self.assertEqual(song['seconds'], 123)
        self.assertTrue(song['cached'])

    def test_cache_ignores_partial_zero_sidecar_and_unknown_files(self):
        root = yandex.cache_dir()
        for name in ('42.flac.tmp', '42.meta.json', '42.html', '42.mp3'):
            (root / name).write_bytes(b'' if name.endswith('mp3') else b'broken')
        self.assertIsNone(yandex.cached_audio('42'))
        self.assertEqual(yandex.cached_tracks(), [])

    def test_ids_cannot_escape_cache_directory(self):
        for identity in ('../42', '/42', 'ym:../../x', '42/33', '42\\33', '', '42.foo'):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                yandex.cached_audio(identity)

    def test_download_commits_audio_and_compatible_metadata(self):
        with patch.object(yandex, 'Api') as api, patch.object(yandex, 'urlopen', return_value=Download()) as fetch:
            api.return_value.file_info.return_value = {'url': 'https://cdn.example/audio', 'codec': 'flac'}
            api.return_value.tracks.return_value = [TRACK]
            result = yandex.run({'op': 'buffer', 'id': 'ym:42'})
        self.assertEqual(Path(result['file']).read_bytes(), b'audio')
        self.assertEqual(fetch.call_args.args, ('https://cdn.example/audio',))
        self.assertEqual(json.loads((yandex.cache_dir() / '42.meta.json').read_text())['artists'], ['Artist'])
        self.assertEqual(list(yandex.cache_dir().glob('*.tmp')), [])

    def test_truncated_download_never_becomes_cache_hit(self):
        with patch.object(yandex, 'Api') as api, patch.object(yandex, 'urlopen', return_value=Download(expected='99')):
            api.return_value.file_info.return_value = {'url': 'https://cdn.example/audio', 'codec': 'flac'}
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                yandex.run({'op': 'buffer', 'id': 'ym:42'})
        self.assertIsNone(yandex.cached_audio('42'))
        self.assertEqual(list(yandex.cache_dir().iterdir()), [])

    def test_cross_filesystem_playback_falls_back_to_copy(self):
        self.cache()
        playback = self.root / 'playback'
        playback.mkdir()
        with patch.object(yandex.os, 'link', side_effect=OSError('EXDEV')):
            result = yandex.buffer({'id': '42', 'directory': str(playback)})
        self.assertEqual(Path(result['file']).read_bytes(), b'audio')

    def test_normalization_namespaces_remote_ids(self):
        song = yandex.normalize(TRACK)
        self.assertEqual(song['videoId'], 'ym:42')
        self.assertEqual(song['albumId'], 'ym:9')
        self.assertEqual(song['artistId'], 'ym:8')
        self.assertEqual(song['art'], 'https://example.com/400x400')
        playlist = yandex.normalize({'kind': 7, 'owner': {'uid': 11}, 'title': 'List'}, 'playlist')
        self.assertEqual(playlist['browseId'], 'ym:11:7')
        self.assertEqual(playlist['videoId'], '')

    def test_dotenv_is_data_not_executable_shell(self):
        env = self.root / 'token.env'
        env.write_text("export YANDEX_MUSIC_TOKEN='literal$(touch /tmp/never-run)'\n")
        with patch.dict(os.environ, {'YANDEX_MUSIC_ENV_FILE': str(env)}):
            self.assertEqual(yandex.token(), 'literal$(touch /tmp/never-run)')

    def test_file_info_accepts_lossless_without_size(self):
        with patch.dict(os.environ, {'YANDEX_MUSIC_TOKEN': 'test-token'}):
            api = yandex.Api()
        with patch.object(api, 'get', return_value={'downloadInfo': {'codec': 'flac', 'url': 'https://cdn.example/a'}}) as call, patch.object(yandex.time, 'time', return_value=1700000000):
            info = api.file_info('ym:42')
        self.assertEqual(info['codec'], 'flac')
        params = call.call_args.args[1]
        self.assertEqual(params['quality'], 'lossless')
        self.assertEqual(params['trackId'], '42')
        self.assertEqual(params['sign'], 'yET0BsHcAOKnvEUBe3nVbRVRyWnmZ3BKcmZsxqHe8v8')

    def test_auth_errors_do_not_expose_credentials(self):
        with patch.dict(os.environ, {'YANDEX_MUSIC_TOKEN': 'secret-token'}):
            api = yandex.Api()
        with patch.object(yandex, 'urlopen', side_effect=HTTPError('https://example', 401, 'secret-token', {}, None)):
            with self.assertRaisesRegex(ValueError, 'denied access') as error:
                api.get('account/status')
        self.assertNotIn('secret-token', str(error.exception))

    def test_catalog_protocol_in_subprocess(self):
        self.cache()
        result = subprocess.run([sys.executable, 'helper/catalog.py'], input=json.dumps({'op': 'home'}), text=True, capture_output=True, cwd=Path(__file__).parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
