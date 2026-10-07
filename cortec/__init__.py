"""
Cortec — local-first memory server for developer workflows.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("cortec-mcp")
except PackageNotFoundError:  # package not installed (e.g. running from source tree)
    __version__ = "0.0.0"

__author__ = "Raj Kumar Satya"
