#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
prefix="${1:-$HOME/.local}"
"$root/scripts/build.sh"
cmake --install "$root/build" --prefix "$prefix"
if command -v gtk-update-icon-cache >/dev/null; then gtk-update-icon-cache -f -t "$prefix/share/icons/hicolor"; fi
if command -v update-desktop-database >/dev/null; then update-desktop-database "$prefix/share/applications"; fi
printf 'Installed Sung Yandex to %s/bin/sung-yandex\n' "$prefix"
