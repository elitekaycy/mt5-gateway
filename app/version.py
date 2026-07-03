"""Application version sourced from the repository VERSION file."""

from pathlib import Path


def get_version():
    candidates = (
        Path(__file__).resolve().parent.parent / "VERSION",
        Path("/VERSION"),
    )
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return "0.0.0+unknown"
