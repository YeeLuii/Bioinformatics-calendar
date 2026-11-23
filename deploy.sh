#!/bin/sh
# Reuse a compatible runtime; no downloads, package installs or shell profile edits.
set -eu
ai4s_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ai4s_probe='import sys,sqlite3,ssl,http.server,ctypes; assert (3,9)<=sys.version_info[:2]<(4,0); print(sys.executable)'
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
    if "$VIRTUAL_ENV/bin/python" -X utf8 -c "$ai4s_probe" >/dev/null 2>&1; then
        exec "$VIRTUAL_ENV/bin/python" -B "$ai4s_root/deploy.py" "$@"
    fi
fi
if [ -x "$ai4s_root/.venv/bin/python" ]; then
    if "$ai4s_root/.venv/bin/python" -X utf8 -c "$ai4s_probe" >/dev/null 2>&1; then
        exec "$ai4s_root/.venv/bin/python" -B "$ai4s_root/deploy.py" "$@"
    fi
fi
for ai4s_candidate in python3 python; do
    if command -v "$ai4s_candidate" >/dev/null 2>&1 && "$ai4s_candidate" -X utf8 -c "$ai4s_probe" >/dev/null 2>&1; then
        exec "$ai4s_candidate" -B "$ai4s_root/deploy.py" "$@"
    fi
done
echo 'Python >=3.9,<4.0 with sqlite3, ssl, http.server and ctypes is required. No runtime or packages were installed.' >&2
exit 1
