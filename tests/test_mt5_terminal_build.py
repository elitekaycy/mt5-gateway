"""Tests for scripts/mt5-terminal-build.py (baked-terminal build sniffing)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mt5-terminal-build.py"
_spec = importlib.util.spec_from_file_location("mt5_terminal_build", _SCRIPT)
mt5_terminal_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt5_terminal_build)


def _utf16le(text: str) -> bytes:
    return text.encode("utf-16-le")


def _version_resource(version: str) -> bytes:
    return (
        _utf16le("Client Terminal")
        + b"\x00" * 6
        + _utf16le("FileVersion")
        + b"\x00" * 4
        + _utf16le(version)
    )


def test_extracts_fileversion_quad_from_version_resource(tmp_path: Path) -> None:
    blob = b"\xff" * 64 + _version_resource("5.0.0.6109") + b"\x00" * 64
    exe = tmp_path / "terminal64.exe"
    exe.write_bytes(blob)
    assert mt5_terminal_build.terminal_build(str(exe)) == "5.0.0.6109"


def test_fileversion_wins_over_noise_versions_earlier_in_binary(tmp_path: Path) -> None:
    blob = _utf16le("10.0.19041") + b"\x00" * 32 + _version_resource("5.0.0.5480")
    exe = tmp_path / "terminal64.exe"
    exe.write_bytes(blob)
    assert mt5_terminal_build.terminal_build(str(exe)) == "5.0.0.5480"


def test_falls_back_to_first_mt5_like_version_without_key(tmp_path: Path) -> None:
    blob = _utf16le("4.0.30319") + b"\x00" * 16 + _utf16le("5.0.4410")
    exe = tmp_path / "terminal64.exe"
    exe.write_bytes(blob)
    assert mt5_terminal_build.terminal_build(str(exe)) == "5.0.4410"


def test_ignores_ascii_version_strings(tmp_path: Path) -> None:
    exe = tmp_path / "terminal64.exe"
    exe.write_bytes(b"FileVersion 5.0.0.6109 ascii only")
    assert mt5_terminal_build.terminal_build(str(exe)) == "unknown"


def test_unknown_when_no_match(tmp_path: Path) -> None:
    exe = tmp_path / "terminal64.exe"
    exe.write_bytes(b"\x00" * 128)
    assert mt5_terminal_build.terminal_build(str(exe)) == "unknown"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        mt5_terminal_build.terminal_build(str(tmp_path / "nope.exe"))
