#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
unset PYTHONPATH PYTHONHOME
exec "$task_root/runtime/python/bin/python3.13" -I -B "$task_root/app/start.py" "$@"
