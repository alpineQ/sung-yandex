"""Secret Service credentials. Tokens only travel through stdin, never argv/files."""
import os
import subprocess

SERVICE = 'sung-yandex'


def secret_tool(action, value=None, service=SERVICE):
    if os.environ.get('SUNG_YANDEX_DISABLE_KEYRING') == '1':
        if action == 'lookup':
            return ''
        raise ValueError('System keyring is disabled.')
    args = ['secret-tool', action]
    if action == 'store':
        args += ['--label=Sung Yandex Music']
    args += ['service', service, 'username', 'default']
    try:
        result = subprocess.run(args, input=value, text=True, capture_output=True, timeout=25)
    except (OSError, subprocess.TimeoutExpired):
        if action == 'lookup':
            return ''
        raise ValueError('Cannot access the system keyring. Install libsecret and unlock your Secret Service keyring, or connect for this session only.') from None
    if result.returncode and action not in ('lookup', 'clear'):
        raise ValueError('The system keyring could not save the token. Unlock it or connect for this session only.')
    if action == 'clear' and result.returncode and (result.returncode != 1 or result.stderr.strip()):
        raise ValueError('The system keyring could not remove the saved token.')
    return result.stdout.strip() if action == 'lookup' and result.returncode == 0 else ''


def load():
    return secret_tool('lookup') or secret_tool('lookup', service='yamusic')


def connect(req):
    from yandex import Api
    value = str(req.get('token', '')).strip()
    if not value or any(c in value for c in '\r\n\0'):
        raise ValueError('Enter a valid Yandex Music OAuth token.')
    account = Api(value).get('account/status')['account']
    if req.get('remember', True):
        secret_tool('store', value)
    return {'uid': str(account['uid']), 'accountName': account.get('displayName') or account.get('login', ''),
            'remembered': bool(req.get('remember', True))}
