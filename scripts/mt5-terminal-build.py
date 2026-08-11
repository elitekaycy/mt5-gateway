#!/usr/bin/env python3
"""Best-effort extraction of the MetaTrader 5 build from terminal64.exe.

The PE StringFileInfo resource stores UTF-16LE entries; the terminal's build is
the value following the "FileVersion" key (e.g. "5.0.0.6109"). Scan for that
key first, then fall back to any plausible "5.0.*" dotted version, instead of
pulling in a PE parser. Used at image build time to record the baked terminal
build in .mt5-install-info. Prints the build, or "unknown" when nothing
plausible is found.
"""

import re
import sys

# A dotted version (triple or quad) in UTF-16LE: each ASCII digit/dot followed
# by a NUL byte.
_VERSION = re.compile(
    rb"(?:[0-9]\x00)+\.\x00(?:[0-9]\x00)+\.\x00(?:[0-9]\x00)+(?:\.\x00(?:[0-9]\x00)+)?"
)
_FILE_VERSION_KEY = "FileVersion".encode("utf-16-le")


def _decode(match: re.Match[bytes]) -> str:
    return match.group().decode("utf-16-le")


def terminal_build(path: str) -> str:
    """Return the terminal's FileVersion string, or "unknown".

    Args:
        path: Path to terminal64.exe.

    Returns:
        The version string (e.g. "5.0.0.6109"), or "unknown".
    """
    with open(path, "rb") as fh:
        data = fh.read()
    key_at = data.find(_FILE_VERSION_KEY)
    if key_at != -1:
        match = _VERSION.search(data, key_at + len(_FILE_VERSION_KEY))
        if match:
            return _decode(match)
    for match in _VERSION.finditer(data):
        candidate = _decode(match)
        if candidate.startswith("5.0."):
            return candidate
    return "unknown"


if __name__ == "__main__":
    print(terminal_build(sys.argv[1]))
