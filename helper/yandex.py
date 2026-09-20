"""Yandex Music adapter for Sung's one-request JSON protocol.

API headers, lossless file-info and cache sidecars ported from yamusic.
GPL-3.0; see NOTICE. No third-party Python dependencies.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

CODECS = ('flac', 'aac', 'he-aac', 'mp3', 'flac-mp4', 'aac-mp4', 'he-aac-mp4')
SIGN_KEY = b'p93jhgh689SBReK6ghtw62'  # Public API protocol key, not an account credential.
MAX_AUDIO = 512 * 1024 * 1024


def token():
    if os.environ.get('SUNG_YANDEX_LOGGED_OUT') == '1':
        return ''
    value = os.environ.get('YANDEX_MUSIC_TOKEN', '').strip()
    if value:
        return value
    filename = os.environ.get('YANDEX_MUSIC_ENV_FILE')
    if filename:
        # Read dotenv data without evaluating shell code or logging credentials.
        for line in Path(filename).expanduser().read_text().splitlines():
            key, sep, value = line.strip().removeprefix('export ').partition('=')
            if sep and key.strip() == 'YANDEX_MUSIC_TOKEN':
                return value.strip().strip('\"\'')
    from yandex_credentials import load
    return load()


def cache_dir():
    configured = os.environ.get('YANDEX_MUSIC_CACHE_DIR')
    if not configured:
        config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'yamusic/config.toml'
        try:
            configured = tomllib.loads(config.read_text()).get('cache-dir')
        except (OSError, ValueError):
            pass
    return Path(configured).expanduser().absolute() if configured else Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'yamusic'


def track_id(value):
    value = str(value).removeprefix('ym:')
    if not re.fullmatch(r'\d+(?::\d+)?', value):
        raise ValueError('Invalid Yandex track ID')
    return value


def numeric_id(value):
    value = str(value)
    if not re.fullmatch(r'\d+', value):
        raise ValueError('Invalid Yandex ID')
    return value


def cached_audio(identity):
    identity = track_id(identity)
    root = cache_dir()
    # The same <id>.<codec> format as yamusic, never a sidecar or partial file.
    for codec in CODECS:
        path = root / f'{identity}.{codec}'
        if path.is_file() and not path.is_symlink() and path.stat().st_size > 0:
            return path
    return None


def cover(item):
    uri = item.get('coverUri') or item.get('ogImage') or (item.get('cover') or {}).get('uri') or ''
    if not uri:
        return ''
    return ('https://' + uri.removeprefix('https://').removeprefix('http://')).replace('%%', '400x400')


def normalize(item, kind='song'):
    item = item.get('track') or item
    raw = str(item.get('id', ''))
    if kind == 'playlist':
        raw = f"{(item.get('owner') or {}).get('uid', '')}:{item.get('kind', '')}"
    identity = 'ym:' + raw
    album = (item.get('albums') or [{}])[0]
    artists = item.get('artists') or []
    seconds = int(item.get('durationMs') or 0) // 1000
    return dict(id=identity, videoId=identity if kind == 'song' else '',
                browseId=identity if kind != 'song' else '', source='yandex', kind=kind,
                title=item.get('title') or item.get('name') or 'Untitled',
                artist=', '.join(a.get('name', '') for a in artists),
                artistId=('ym:' + str(artists[0]['id'])) if artists and artists[0].get('id') else '',
                album=album.get('title', ''), albumId=('ym:' + str(album['id'])) if album.get('id') else '',
                art=cover(item) or cover(album), seconds=seconds,
                duration=f'{seconds // 60}:{seconds % 60:02d}' if seconds else '',
                available=item.get('available', True), explicit=item.get('contentWarning') == 'explicit')


def cached_tracks():
    items = []
    for path in sorted(cache_dir().glob('*.meta.json')):
        try:
            meta = json.loads(path.read_text())
            if not cached_audio(meta['id']):
                continue
            raw = dict(id=meta['id'], title=meta.get('title'), artists=[{'name': a} for a in meta.get('artists', [])],
                       albums=[{'title': meta.get('album')}], coverUri=meta.get('cover_uri'), durationMs=meta.get('duration_ms'))
            item = normalize(raw)
            item['cached'] = True
            items.append(item)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return items


class Api:
    def __init__(self, oauth_token=None):
        self.token = token() if oauth_token is None else oauth_token
        if not self.token:
            raise ValueError('Set your Yandex Music OAuth token in Settings → Connections, or YANDEX_MUSIC_TOKEN. Downloaded songs work offline.')

    def get(self, path, params=None, data=None, json_data=None):
        url = 'https://api.music.yandex.net/' + path
        if params:
            url += '?' + urlencode(params)
        body = json.dumps(json_data).encode() if json_data is not None else urlencode(data, doseq=True).encode() if data is not None else None
        request = Request(url, data=body, headers={
            'Content-Type': 'application/json' if json_data is not None else 'application/x-www-form-urlencoded',
            'Authorization': 'OAuth ' + self.token,
            'X-Yandex-Music-Client': 'YandexMusicAndroid/24023621',
            'Origin': 'music-application://desktop', 'Accept-Language': 'ru',
            'User-Agent': 'YandexMusic/5.82.0',
        })
        try:
            with urlopen(request, timeout=15) as response:
                result = json.load(response)
        except HTTPError as exc:
            if exc.code == 409:
                raise ValueError('This playlist changed on another device. Refresh it before editing again.') from None
            if exc.code in (401, 403):
                raise ValueError('Yandex Music denied access. Check your OAuth token and subscription.') from None
            raise ValueError(f'Yandex Music HTTP error {exc.code}. Try again.') from None
        except (URLError, TimeoutError):
            raise ValueError('Cannot connect to Yandex Music. Downloaded songs are available on Home.') from None
        if 'error' in result:
            raise ValueError('Yandex Music could not complete this request.')
        return result['result']

    def tracks(self, ids):
        tracks = []
        for offset in range(0, len(ids), 100):
            tracks.extend(self.get('tracks', data={'track-ids': ','.join(ids[offset:offset + 100])}))
        return tracks

    def file_info(self, identity):
        identity = track_id(identity)
        ts = str(int(time.time()))
        message = ts + identity + 'lossless' + ''.join(CODECS) + 'raw'
        signature = base64.b64encode(hmac.new(SIGN_KEY, message.encode(), hashlib.sha256).digest()).decode().rstrip('=')
        # Deliberately do not require size: Yandex omits it on some lossless files.
        return self.get('get-file-info', dict(ts=ts, trackId=identity, quality='lossless',
                                            codecs=','.join(CODECS), transports='raw', sign=signature))['downloadInfo']


def save_meta(identity, raw):
    root = cache_dir()
    album = (raw.get('albums') or [{}])[0]
    meta = dict(id=identity, title=raw.get('title'), artists=[a.get('name', '') for a in raw.get('artists', [])],
                album=album.get('title'), cover_uri=raw.get('coverUri') or album.get('coverUri'), duration_ms=raw.get('durationMs'))
    fd, temporary = tempfile.mkstemp(prefix=identity + '.', suffix='.tmp', dir=root)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(meta, out, ensure_ascii=False)
        os.replace(temporary, root / f'{identity}.meta.json')
    finally:
        Path(temporary).unlink(missing_ok=True)


def buffer(req):
    identity = track_id(req['id'])
    audio = cached_audio(identity)
    if audio is None:
        api = Api()
        info = api.file_info(identity)
        codec = info.get('codec')
        if codec not in CODECS or urlparse(info.get('url', '')).scheme != 'https':
            raise ValueError('Yandex returned an unsupported audio format or URL.')
        root = cache_dir()
        root.mkdir(parents=True, exist_ok=True)
        audio = root / f'{identity}.{codec}'
        # Unique staging files support concurrent playback and next-track preparation.
        fd, temporary = tempfile.mkstemp(prefix=identity + '.', suffix='.tmp', dir=root)
        try:
            # Never forward OAuth headers to the audio CDN.
            with os.fdopen(fd, 'wb') as out, urlopen(info['url'], timeout=25) as response:
                if urlparse(response.geturl()).scheme != 'https':
                    raise ValueError('Audio download redirected to an insecure URL.')
                expected = int(response.headers.get('Content-Length') or 0)
                if expected > MAX_AUDIO:
                    raise ValueError('Track exceeds the 512 MiB download limit.')
                total = 0
                while chunk := response.read(256 * 1024):
                    total += len(chunk)
                    if total > MAX_AUDIO:
                        raise ValueError('Track exceeds the 512 MiB download limit.')
                    out.write(chunk)
                if not total or (expected and total != expected):
                    raise ValueError('Incomplete audio download. Try again.')
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, audio)
        finally:
            Path(temporary).unlink(missing_ok=True)
        try:
            save_meta(identity, api.tracks([identity])[0])
        except (OSError, ValueError, IndexError):
            pass  # An unavailable metadata endpoint must not stop valid audio.
    if req.get('directory'):
        # Sung accepts only files in its private QTemporaryDir. A hardlink keeps
        # the existing lifetime and crossfade rules, without duplicating audio.
        directory = Path(req['directory']).resolve(strict=True)
        target = directory / audio.name
        if not target.exists():
            try:
                os.link(audio, target)
            except OSError:
                shutil.copyfile(audio, target)
        return {'file': str(target)}
    return {'file': str(audio)}


def collection(api, identity):
    owner, kind = identity.split(':')
    data = api.get(f'users/{numeric_id(owner)}/playlists/{numeric_id(kind)}', {'rich-tracks': 'true'})
    tracks = data.get('tracks') or []
    raw = [t.get('track') for t in tracks]
    if any(t is None for t in raw):
        raw = api.tracks([str(t['id']) for t in tracks])
    return dict(title=data.get('title', ''), art=cover(data), items=[normalize(t) for t in raw], total=data.get('trackCount', len(raw)))


def run(req):
    op = req.get('op')
    if op == 'account-connect':
        from yandex_credentials import connect
        return connect(req)
    if op == 'account-forget':
        from yandex_credentials import secret_tool
        secret_tool('clear')
        return {}
    if op in ('buffer', 'resolve'):
        return buffer(req)
    if op == 'home':
        offline = cached_tracks()
        sections = [{'title': 'Downloaded · Offline', 'items': offline}] if offline else []
        try:
            api = Api()
            account = api.get('account/status')['account']
            uid = account['uid']
            playlists = api.get(f'users/{uid}/playlists/list')
            sections.append({'title': 'Yandex Music', 'items': [dict(id=f'ym:{uid}:3', browseId=f'ym:{uid}:3', kind='playlist', title='Мне нравится', source='yandex')]})
            sections.append({'title': 'Мои плейлисты', 'items': [normalize(p, 'playlist') for p in playlists]})
        except (ValueError, OSError):
            if not offline:
                raise
        result = {'sections': sections}
        if 'account' in locals():
            result.update(uid=str(uid), accountName=account.get('displayName') or account.get('login', ''))
        return result
    api = Api()
    identity = str(req.get('id', '')).removeprefix('ym:')
    if op == 'search':
        kinds = {'songs': ('tracks', 'song'), 'albums': ('albums', 'album'), 'artists': ('artists', 'artist'), 'playlists': ('playlists', 'playlist')}
        selected = kinds.get(req.get('filter'))
        data = api.get('search', {'text': req['query'], 'type': {'tracks': 'track', 'albums': 'album', 'artists': 'artist', 'playlists': 'playlist'}[selected[0]] if selected else 'all', 'page': 0, 'page-size': min(int(req.get('limit', 30)), 200)})
        items = []
        for key, kind in ([selected] if selected else kinds.values()):
            items.extend(normalize(t, kind) for t in (data.get(key) or {}).get('results', []))
        return {'items': items}
    if op == 'playlist':
        return collection(api, identity)
    if op == 'album':
        data = api.get(f'albums/{numeric_id(identity)}/with-tracks')
        return dict(title=data.get('title', ''), art=cover(data), year=str(data.get('year', '')),
                    artist=', '.join(a.get('name', '') for a in data.get('artists', [])),
                    items=[normalize(t) for volume in data.get('volumes', []) for t in volume])
    if op == 'artist':
        page = max(0, int(req.get('page', 0)))
        data = api.get(f'artists/{numeric_id(identity)}/tracks', {'page-size': 100, 'page': page})
        info = api.get(f'artists/{identity}/brief-info')['artist'] if page == 0 else {}
        tracks = [normalize(t) for t in data.get('tracks', [])]
        pager = data.get('pager') or {}
        total = int(pager.get('total', (page + 1) * 100 + (1 if len(tracks) == 100 else 0)))
        result = dict(items=tracks, nextPage=page + 1, hasMore=(page * 100 + len(tracks)) < total, total=total)
        if page == 0:
            result.update(title=info.get('name', ''), art=cover(info))
        return result
    if op == 'radio':
        data = api.get(f'tracks/{track_id(identity)}/similar')
        return {'items': [normalize(t) for t in data.get('similarTracks', [])]}
    if op == 'lyrics':
        ts = str(int(time.time()))
        signature = base64.b64encode(hmac.new(SIGN_KEY, (track_id(identity) + ts).encode(), hashlib.sha256).digest()).decode()
        data = api.get(f'tracks/{identity}/lyrics', {'format': 'LRC', 'timeStamp': ts, 'sign': signature})
        if urlparse(data['downloadUrl']).scheme != 'https':
            raise ValueError('Invalid lyrics URL')
        with urlopen(data['downloadUrl'], timeout=10) as response:
            lyrics = response.read(1024 * 1024).decode()
        return {'lrc': lyrics, 'lyrics': lyrics, 'source': 'Yandex Music'}
    if op == 'link':
        parsed = urlparse(req['url'])
        if parsed.scheme != 'https' or parsed.hostname not in ('music.yandex.ru', 'music.yandex.com', 'music.yandex.kz', 'music.yandex.by'):
            raise ValueError('Paste a Yandex Music album, track, artist or playlist link.')
        path = parsed.path.strip('/')
        match = re.fullmatch(r'(?:album/\d+/)?track/(\d+)', path)
        if match:
            tracks = api.tracks([match[1]])
            return {'title': tracks[0].get('title', ''), 'items': [normalize(t) for t in tracks]}
        match = re.fullmatch(r'(album|artist)/(\d+)', path)
        if match:
            return run({'op': match[1], 'id': match[2]})
        match = re.fullmatch(r'users/([^/]+)/playlists/(\d+)', path)
        if match:
            from urllib.parse import quote
            data = api.get(f'users/{quote(match[1], safe="")}/playlists/{match[2]}')
            return collection(api, f"{data['owner']['uid']}:{match[2]}")
        raise ValueError('Unsupported Yandex Music link.')
    raise ValueError('Unsupported Yandex Music operation.')
