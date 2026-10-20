"""The boot script that clears an X display lock left from before a restart."""

import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "root"
    / "custom-cont-init.d"
    / "10-clear-stale-x-lock"
)


def _run(tmp: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={"X_TMP": str(tmp), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


def test_a_lock_left_from_before_the_restart_is_removed(tmp_path):
    # bot1 2026-10-20: the lock named pid 206, which after the host reboot was nginx, so Xvnc refused to start.
    (tmp_path / ".X0-lock").write_text("       206\n")
    (tmp_path / ".X11-unix").mkdir()
    (tmp_path / ".X11-unix" / "X0").touch()

    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".X0-lock").exists()
    assert not (tmp_path / ".X11-unix" / "X0").exists()
    assert "206" in result.stdout


def test_a_clean_boot_has_nothing_to_remove(tmp_path):
    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
