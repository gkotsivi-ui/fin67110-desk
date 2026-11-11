#!/bin/bash
# Starts the agent team's page and opens it in your browser. Keep this window open; close it to stop the page.
cd "$(dirname "$0")" || exit 1
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi
if command -v python3 >/dev/null 2>&1; then python3 page.py; else python page.py; fi
