#!/usr/bin/env bash
set -euo pipefail

: "${INTERNAL_PYPI_URL:?INTERNAL_PYPI_URL required}"
: "${INTERNAL_PYPI_TOKEN:?INTERNAL_PYPI_TOKEN required}"

python -m build
python -m pip install --upgrade twine
python -m twine upload --repository-url "$INTERNAL_PYPI_URL" -u "__token__" -p "$INTERNAL_PYPI_TOKEN" dist/*
