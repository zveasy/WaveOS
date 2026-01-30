from __future__ import annotations

from importlib import metadata


def current_version() -> str:
    try:
        return metadata.version("waveos")
    except metadata.PackageNotFoundError:
        return "0.0.0"
