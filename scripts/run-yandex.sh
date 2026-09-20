#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
# Optional read-only reuse of the adjacent yamusic dotenv file. Python parses it
# as data; it is never sourced as shell code or copied into this repository.
if [[ -z "${YANDEX_MUSIC_TOKEN:-}" && -z "${YANDEX_MUSIC_ENV_FILE:-}" && -f "$root/../yamusic/.env" ]]; then
    export YANDEX_MUSIC_ENV_FILE="$root/../yamusic/.env"
fi
export SUNG_HELPER="$root/helper/catalog.py"
if [[ -f /etc/NIXOS ]]; then
    exec nix develop --command bash -c '
        if [[ ! -x build/sung-yandex ]]; then
            cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
            cmake --build build --target sung -j "${SUNG_BUILD_JOBS:-4}"
        fi
        exec build/sung-yandex "$@"
    ' -- "$@"
fi
if [[ ! -x build/sung-yandex ]]; then "$root/scripts/build.sh"; fi
exec "$root/build/sung-yandex" "$@"
