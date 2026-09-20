"""Persistent artwork/LRC companions to yamusic audio cache files."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen


def atomic_write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(contents)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def artwork_path(url):
    from yandex import cache_dir
    return cache_dir() / 'artwork' / (hashlib.sha256(url.encode()).hexdigest() + '.img')


def local_artwork(url):
    path = artwork_path(url)
    return path.as_uri() if path.is_file() and path.stat().st_size else url


def lyric_path(identity):
    from yandex import cache_dir, track_id
    return cache_dir() / 'lyrics' / (track_id(identity) + '.lrc')


def cached_lyrics(identity):
    path = lyric_path(identity)
    try:
        text = path.read_text()
        return {'lrc': text, 'lyrics': text, 'source': 'Yandex Music · Offline'} if text else None
    except OSError:
        return None


def lyrics(identity, api=None):
    from yandex import Api, track_id, SIGN_KEY
    identity = track_id(identity)
    found = cached_lyrics(identity)
    if found: return found
    api = api or Api()
    ts = str(int(time.time()))
    signature = base64.b64encode(hmac.new(SIGN_KEY, (identity + ts).encode(), hashlib.sha256).digest()).decode()
    data = api.get(f'tracks/{identity}/lyrics', {'format': 'LRC', 'timeStamp': ts, 'sign': signature})
    if urlparse(data['downloadUrl']).scheme != 'https':
        raise ValueError('Invalid lyrics URL')
    with urlopen(data['downloadUrl'], timeout=10) as response:
        payload = response.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise ValueError('Lyrics are too large.')
    text = payload.decode('utf-8-sig')
    if text.strip():
        atomic_write(lyric_path(identity), text.encode())
    return {'lrc': text, 'lyrics': text, 'source': 'Yandex Music'}


def companions(identity):
    from yandex import Api, cache_dir, cover, track_id, save_meta
    identity = track_id(identity)
    warnings = []
    metadata = cache_dir() / f'{identity}.meta.json'
    try:
        meta = json.loads(metadata.read_text())
    except (OSError, ValueError):
        api = Api()
        tracks = api.tracks([identity])
        if not tracks: return {'warnings': ['Track metadata is unavailable.']}
        save_meta(identity, tracks[0])
        meta = json.loads(metadata.read_text())
    url = cover({'coverUri': meta.get('cover_uri')})
    if url and urlparse(url).scheme == 'https':
        try:
            with urlopen(url, timeout=12) as response:
                payload = response.read(8 * 1024 * 1024 + 1)
                content_type = response.headers.get('Content-Type', '')
            if len(payload) > 8 * 1024 * 1024 or not payload or not content_type.startswith('image/'):
                raise ValueError('Invalid artwork response')
            atomic_write(artwork_path(url), payload)
        except (OSError, ValueError):
            warnings.append('Artwork is not available offline yet.')
    try:
        lyrics(identity)
    except (OSError, ValueError):
        warnings.append('Lyrics are unavailable or could not be downloaded.')
    return {'art': local_artwork(url) if url else '', 'lyricsCached': bool(cached_lyrics(identity)), 'warnings': warnings}


def run(req):
    from yandex import buffer, cached_tracks, cache_dir
    op = req['op']
    if op == 'yandex-cache-list':
        return {'items': cached_tracks()}
    if op == 'yandex-cache':
        result = buffer({'id': req['id']})
        # Audio success is independent of optional artwork/lyrics availability.
        try:
            result.update(companions(req['id']))
        except (OSError, ValueError):
            result['warnings'] = ['Audio saved; companion downloads will be retried later.']
        return result
    if op == 'yandex-cache-prune':
        return prune(req.get('limitBytes', 0), protected=tuple(str(t).removeprefix('ym:') for t in req.get('protected', [])))
    if op == 'yandex-cache-assets':
        return companions(req['id'])
    raise ValueError('Unknown cache operation')


def prune(max_bytes, protected=()):
    """Remove least recently used complete audio only after an explicit quota choice."""
    from yandex import cache_dir, CODECS, track_id
    limit = max(0, int(max_bytes))
    if not limit: return {'removed': 0}
    root = cache_dir()
    candidates = []
    for codec in CODECS:
        for path in root.glob('*.' + codec):
            try:
                identity = track_id(path.name[:-len(codec) - 1])
                if path.is_symlink() or not path.is_file(): continue
                stat = path.stat()
                candidates.append((stat.st_atime_ns, path, identity, stat.st_size))
            except (ValueError, OSError):
                continue
    size = sum(row[3] for row in candidates)
    removed = 0
    for _, path, identity, length in sorted(candidates):
        if size <= limit: break
        if identity in protected: continue
        try:
            path.unlink()
            size -= length; removed += 1
            # Preserve sidecars if another quality of this song still exists.
            if not any((root / f'{identity}.{codec}').exists() for codec in CODECS):
                (root / f'{identity}.meta.json').unlink(missing_ok=True)
                lyric_path(identity).unlink(missing_ok=True)
        except OSError:
            continue
    return {'removed': removed, 'audioBytes': size}
