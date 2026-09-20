"""Yandex library reads and revision-checked mutations."""
import json


def owned(api, identity):
    from yandex import numeric_id
    owner, kind = identity.removeprefix('ym:').split(':')
    numeric_id(owner); numeric_id(kind)
    uid = str(api.get('account/status')['account']['uid'])
    if uid != owner or kind == '3':
        raise ValueError('Only your own regular Yandex playlists can be edited.')
    return f'users/{owner}/playlists/{kind}', owner, kind


def playlist_data(api, raw):
    from yandex import normalize
    # Mutation responses can contain only summary fields, even when tracks exist.
    if int(raw.get('trackCount') or 0) > len(raw.get('tracks') or []):
        owner = raw['owner']['uid']
        full = api.get(f"users/{owner}/playlists/{raw['kind']}")
        raw = {**raw, **full}
    result = normalize(raw, 'playlist')
    wrappers = raw.get('tracks') or []
    ids = [str(t['id']) for t in wrappers if not t.get('track')]
    resolved = {str(t['id']): t for t in api.tracks(ids)} if ids else {}
    result.update(remote=True, revision=int(raw.get('revision', 0)),
                  tracks=[normalize(t.get('track') or resolved[str(t['id'])]) for t in wrappers],
                  count=raw.get('trackCount', len(wrappers)), loaded=True)
    return result


def track_refs(api, tracks):
    from yandex import track_id, numeric_id
    refs = []
    for item in tracks:
        if not str(item.get('id', '')).startswith('ym:') or item.get('localPath'):
            raise ValueError('Yandex playlists accept Yandex Music tracks only. Use a local playlist for mixed sources.')
        identity = track_id(item['id']).split(':')[0]
        album = str(item.get('albumId') or '').removeprefix('ym:')
        if not album:
            raw = api.tracks([identity])
            album = str((raw[0].get('albums') or [{}])[0].get('id', '')) if raw else ''
        if not album:
            raise ValueError('This track has no album identifier and cannot be added to a Yandex playlist.')
        refs.append({'id': identity, 'albumId': numeric_id(album)})
    return refs


def run(req):
    from yandex import Api, normalize, track_id
    api = Api()
    op = req['op']
    if op == 'yandex-like':
        uid = api.get('account/status')['account']['uid']
        action = 'add-multiple' if req['liked'] else 'remove'
        api.get(f'users/{uid}/likes/tracks/{action}', data={'track-ids': track_id(req['id']).split(':')[0]})
        return {'id': req['id'], 'liked': bool(req['liked'])}
    if op == 'yandex-library':
        account = api.get('account/status')['account']
        uid = account['uid']
        # Playlist 3 matches yamusic and provides full track metadata in one request.
        liked = api.get(f'users/{uid}/playlists/3')
        favorites = playlist_data(api, liked)['tracks']
        playlists = []
        for raw in api.get(f'users/{uid}/playlists/list'):
            p = normalize(raw, 'playlist')
            p.update(remote=True, loaded=False, revision=int(raw.get('revision', 0)), count=raw.get('trackCount', 0))
            playlists.append(p)
        return {'uid': str(uid), 'accountName': account.get('displayName') or account.get('login', ''),
                'favorites': favorites, 'playlists': playlists}
    if op == 'yandex-playlist-create':
        title = str(req.get('title', '')).strip()[:120]
        if not title: raise ValueError('Enter a playlist name.')
        # Validate contents before creating anything on the server.
        refs = track_refs(api, req.get('items', []))
        uid = api.get('account/status')['account']['uid']
        raw = api.get(f'users/{uid}/playlists/create', data={'title': title, 'visibility': 'private'})
        created = playlist_data(api, raw)
        if refs:
            try:
                diff = [{'op': 'insert', 'at': 0, 'tracks': refs}]
                raw = api.get(f"users/{uid}/playlists/{raw['kind']}/change",
                              data={'revision': raw['revision'], 'diff': json.dumps(diff)})
                return {'playlist': playlist_data(api, raw)}
            except ValueError:
                # Preserve the successfully created playlist and make partial success explicit.
                return {'playlist': created, 'warning': 'Playlist created, but tracks were not added. Open it and try adding them again.'}
        return {'playlist': created}
    path, owner, kind = owned(api, str(req['id']))
    raw = api.get(path)
    if op == 'yandex-playlist-get':
        return {'playlist': playlist_data(api, raw)}
    if op == 'yandex-playlist-rename':
        title = str(req.get('title', '')).strip()[:120]
        if not title: raise ValueError('Enter a playlist name.')
        updated = api.get(path + '/name', data={'value': title})
        return {'playlist': playlist_data(api, updated)}
    if op == 'yandex-playlist-delete':
        api.get(path + '/delete', data={})
        return {'deleted': req['id']}
    if op == 'yandex-playlist-edit':
        if int(req.get('revision', -1)) != int(raw.get('revision', 0)):
            raise ValueError('This playlist changed on another device. Refresh it before editing again.')
        refs = track_refs(api, req.get('items', []))
        diff = []
        count = len(raw.get('tracks') or [])
        if count: diff.append({'op': 'delete', 'from': 0, 'to': count})
        if refs: diff.append({'op': 'insert', 'at': 0, 'tracks': refs})
        if diff:
            raw = api.get(path + '/change', data={'revision': raw['revision'], 'diff': json.dumps(diff)})
        return {'playlist': playlist_data(api, raw)}
    if op == 'yandex-playlist-add':
        refs = track_refs(api, req.get('items', []))
        present = {str(t['id']) for t in raw.get('tracks', [])}
        refs = [t for t in refs if t['id'] not in present]
        if refs:
            diff = [{'op': 'insert', 'at': len(raw.get('tracks') or []), 'tracks': refs}]
            raw = api.get(path + '/change', data={'revision': raw['revision'], 'diff': json.dumps(diff)})
        return {'playlist': playlist_data(api, raw)}
    raise ValueError('Unsupported Yandex library operation.')
