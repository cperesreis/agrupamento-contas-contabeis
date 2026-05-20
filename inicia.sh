#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

if ! .venv/bin/python -m streamlit --version >/dev/null 2>&1; then
    .venv/bin/python -m pip install -r requirements.txt
fi

.venv/bin/python -m streamlit run app.py
