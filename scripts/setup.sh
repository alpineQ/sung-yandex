#!/usr/bin/env bash
set -euo pipefail
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
printf 'Yandex Music helper uses the Python standard library; no pip packages required.\n'
