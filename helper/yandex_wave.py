"""Session-based My Wave API used by yamusic, including batched feedback."""
from urllib.parse import quote


def run(req):
    from yandex import Api, normalize, track_id
    api = Api()
    seed = str(req.get('seed', 'user:onyourwave'))
    if seed != 'user:onyourwave':
        if not seed.startswith('track:'):
            raise ValueError('Unsupported wave seed')
        track_id(seed.removeprefix('track:'))
    if req['op'] == 'wave-start':
        data = api.get('rotor/session/new', json_data={'seeds': [seed], 'includeTracksInResponse': True,
                                                     'includeWaveModel': True, 'interactive': True})
    elif req['op'] == 'wave-next':
        session = str(req.get('session', ''))
        if not session or len(session) > 512:
            raise ValueError('Invalid wave session')
        queue = [track_id(t) for t in req.get('queue', [])][-100:]
        data = api.get(f'rotor/session/{quote(session, safe="")}/tracks',
                       json_data={'queue': queue, 'feedbacks': req.get('feedbacks', [])})
        if data.get('unknownSession'):
            return run({'op': 'wave-start', 'seed': seed})
    else:
        raise ValueError('Unknown wave operation')
    session = data.get('radioSessionId') or req.get('session')
    if not session:
        raise ValueError('Yandex did not return a wave session.')
    wave = data.get('wave') or {}
    items = []
    for row in data.get('sequence', []):
        raw = row.get('track')
        if not raw or not raw.get('available', True): continue
        item = normalize(raw)
        item.update(_waveSession=session, _waveBatch=data.get('batchId', ''),
                    _waveFrom=wave.get('idForFrom', req.get('from', '')), _queueOrigin='wave')
        items.append(item)
    return {'session': session, 'batch': data.get('batchId', ''), 'from': wave.get('idForFrom', req.get('from', '')),
            'seed': seed, 'items': items, 'terminated': bool(data.get('terminated'))}
