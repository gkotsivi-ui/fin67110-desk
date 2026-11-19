#!/bin/bash
# Start the group-owned pipeline page with its local Python 3.13 environment.
cd "$(dirname "$0")" || exit 1
if [ -x .venv-desk/bin/python ]; then
  exec .venv-desk/bin/python page.py
fi
echo "Create .venv-desk with Python 3.13 and install requirements-pipeline.txt first."
exit 1
