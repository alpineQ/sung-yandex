"""Session-based My Wave API used by yamusic, including batched feedback."""
import re
from urllib.parse import quote

SETTINGS = ('diversity', 'moodEnergy', 'language')


def seeds_of(req):
    from yandex import track_id
    seeds = [str(s) for s in req.get('seeds') or ['user:onyourwave']]
    if not 0 < len(seeds) <= 8:
        raise ValueError('Unsupported wave seed')
    for seed in seeds:
        if seed.startswith('track:'):
            track_id(seed.removeprefix('track:'))
        elif not re.fullmatch(r'[A-Za-z]+:[A-Za-z0-9_-]{1,64}', seed):
            raise ValueError('Unsupported wave seed')
    return seeds


def settings(api):
    """Wave contexts (activities) and the diversity, mood and language choices."""
    data = api.get('rotor/wave/settings')
    contexts = [{'seed': f"{c['id']['type']}:{c['id']['tag']}", 'name': c['name']}
                for block in data.get('blocks', []) if block.get('type') == 'contexts' for c in block.get('items', [])]
    restrictions = data['settingRestrictions']
    groups = [{'key': key, 'name': restrictions[key]['name'],
               'values': [{'seed': v['serializedSeed'], 'name': v['name'], 'unspecified': bool(v.get('unspecified'))}
                          for v in restrictions[key]['possibleValues']]} for key in SETTINGS]
    return {'contexts': contexts, 'groups': groups}


def run(req):
    from yandex import Api, normalize, track_id
    api = Api()
    if req['op'] == 'wave-settings':
        return settings(api)
    seeds = seeds_of(req)
    if req['op'] == 'wave-start':
        data = api.get('rotor/session/new', json_data={'seeds': seeds, 'includeTracksInResponse': True,
                                                     'includeWaveModel': True, 'interactive': True})
    elif req['op'] == 'wave-next':
        session = str(req.get('session', ''))
        if not session or len(session) > 512:
            raise ValueError('Invalid wave session')
        queue = [track_id(t) for t in req.get('queue', [])][-100:]
        data = api.get(f'rotor/session/{quote(session, safe="")}/tracks',
                       json_data={'queue': queue, 'feedbacks': req.get('feedbacks', [])})
        if data.get('unknownSession'):
            return run({'op': 'wave-start', 'seeds': seeds})
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
            'seeds': seeds, 'title': wave.get('name', ''), 'items': items, 'terminated': bool(data.get('terminated'))}
