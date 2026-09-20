"""Check actual QML transport geometry (run inside the Qt development shell)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

binary = str(Path(sys.argv[1]).resolve())
failed = False
for width, expanded in [(1900, True), (2560, True), (1180, False), (800, False), (480, False)]:
    with tempfile.TemporaryDirectory(prefix='sung-player-layout-') as directory:
        root = Path(directory)
        config = root / 'config/SungYandex/sung-yandex.conf'
        config.parent.mkdir(parents=True)
        config.write_text(f'[General]\nmotion=false\nambientBackdrop=false\n[Window]\nwidth={width}\nheight=800\n[Navigation]\nexpanded={str(expanded).lower()}\n')
        library = root / 'data/SungYandex/sung-yandex/library.json'
        library.parent.mkdir(parents=True)
        library.write_text(json.dumps({'queue': [{'id': 'ym:42', 'videoId': 'ym:42', 'kind': 'song', 'title': 'A long track title ' * 8, 'artist': 'Artist'}], 'index': 0}))
        env = dict(os.environ, XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'),
                   XDG_CACHE_HOME=str(root/'cache'), QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                   SUNG_YANDEX_DISABLE_KEYRING='1', SUNG_YANDEX_LOGGED_OUT='1')
        result = subprocess.run([binary, '--isolated', '--my-wave', '--check-player-layout'], env=env, capture_output=True, text=True, timeout=15)
        print(f'width={width}, expanded={expanded}: {result.stdout.strip()}', flush=True)
        if result.returncode:
            failed = True
            if result.stderr: print(result.stderr[-1500:])
sys.exit(1 if failed else 0)
