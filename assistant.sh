#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$DIR/linkedin_hunter/.venv/bin/python" ]; then
    PYTHON="$DIR/linkedin_hunter/.venv/bin/python"
elif [ -f "$DIR/.venv/bin/python" ]; then
    PYTHON="$DIR/.venv/bin/python"
else
    PYTHON="$(command -v python3)"
fi

export PYTHONPATH="$DIR:$PYTHONPATH"
exec "$PYTHON" -m agent.main "$@"
