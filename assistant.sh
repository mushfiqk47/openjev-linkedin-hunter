#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR/linkedin_hunter/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "Error: Virtual environment not found at $PYTHON"
    exit 1
fi

export PYTHONPATH="$DIR:$PYTHONPATH"
exec "$PYTHON" -m agent.main "$@"
