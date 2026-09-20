#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
# Optional read-only reuse of the adjacent yamusic dotenv file. Python parses it
# as data; it is never sourced as shell code or copied into this repository.
if [[ -z "${YANDEX_MUSIC_TOKEN:-}" && -z "${YANDEX_MUSIC_ENV_FILE:-}" && -f "$root/../yamusic/.env" ]]; then
    export YANDEX_MUSIC_FALLBACK_ENV_FILE="$root/../yamusic/.env"
fi
export SUNG_HELPER="$root/helper/catalog.py"
if [[ -f /etc/NIXOS ]]; then
    exec nix develop --command bash -c '
        cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
        cmake --build build-release --target sung -j "${SUNG_BUILD_JOBS:-4}"
        exec build-release/sung-yandex "$@"
    ' -- "$@"
fi
cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build build-release --target sung -j "${SUNG_BUILD_JOBS:-4}"
exec "$root/build-release/sung-yandex" "$@"
