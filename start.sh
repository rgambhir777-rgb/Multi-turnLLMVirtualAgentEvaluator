#!/usr/bin/env bash
# AgentProof - one-command start for macOS / Linux.
# Creates a virtual environment on first run, installs dependencies, starts the
# server and opens http://localhost:8000 in your browser.
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for candidate in python3.12 python3.13 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11, 3.12 or 3.13 is required. Install it (e.g. 'brew install python@3.12' or your package manager) and retry."
  exit 1
fi

venv_python() {
  # .venv/bin on macOS/Linux, .venv/Scripts when run from Git Bash on Windows
  if [ -x ".venv/bin/python" ]; then echo ".venv/bin/python"; elif [ -x ".venv/Scripts/python.exe" ]; then echo ".venv/Scripts/python.exe"; fi
}

if [ -z "$(venv_python)" ]; then
  echo "Creating virtual environment with $PY ..."
  "$PY" -m venv .venv
fi
VPY="$(venv_python)"

if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "Installing dependencies (first run takes a minute or two) ..."
  "$VPY" -m pip install --disable-pip-version-check -q --upgrade pip
  "$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi

if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env; fi

exec "$VPY" run.py
