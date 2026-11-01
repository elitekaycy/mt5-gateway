"""The VNC and headless images must stay interchangeable on one /config volume."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VNC = (ROOT / "Dockerfile").read_text()
HEADLESS = (ROOT / "Dockerfile.headless").read_text()
BAKE = ROOT / "scripts" / "bake-wine-template.sh"
S6 = ROOT / "root-headless" / "etc" / "s6-overlay" / "s6-rc.d"


def _arg(dockerfile: str, name: str) -> str:
    match = re.search(rf"^ARG {name}=(\S+)$", dockerfile, re.MULTILINE)
    assert match, f"ARG {name} missing"
    return match.group(1)


@pytest.mark.parametrize("name", ["MT5_SETUP_URL", "MT5_SETUP_SHA256"])
def test_both_images_pin_the_same_installer(name):
    assert _arg(VNC, name) == _arg(HEADLESS, name)


def test_the_runtime_fallback_pins_the_same_installer_checksum():
    common = (ROOT / "scripts" / "02-common.sh").read_text()
    assert f'mt5setup_sha256="{_arg(VNC, "MT5_SETUP_SHA256")}"' in common


def test_both_images_pin_the_same_terminal_by_digest():
    pattern = r"^FROM (\S+@sha256:[0-9a-f]{64}) AS terminal-source$"
    pins = [re.findall(pattern, text, re.MULTILINE) for text in (VNC, HEADLESS)]
    assert pins[0] == pins[1]
    assert len(pins[0]) == 1


def test_both_images_install_the_same_wine_build():
    pattern = r"wine-stable-amd64=(\S+)"
    assert re.findall(pattern, VNC) == re.findall(pattern, HEADLESS)
    assert len(re.findall(pattern, VNC)) == 1


@pytest.mark.parametrize("dockerfile", [VNC, HEADLESS], ids=["vnc", "headless"])
def test_both_images_bake_with_the_shared_script(dockerfile):
    assert "RUN /scripts/bake-wine-template.sh runtime" in dockerfile
    assert "/scripts/bake-wine-template.sh terminal" in dockerfile


@pytest.mark.parametrize("dockerfile", [VNC, HEADLESS], ids=["vnc", "headless"])
@pytest.mark.parametrize(
    "setting",
    [
        "HOME=/config",
        "WINEARCH=win64",
        "DISPLAY=:0",
        "WINE_TEMPLATE=/opt/wine-template",
    ],
)
def test_both_images_share_the_volume_settings(dockerfile, setting):
    assert f"ENV {setting}" in dockerfile


@pytest.mark.parametrize("dockerfile", [VNC, HEADLESS], ids=["vnc", "headless"])
def test_both_images_use_one_prefix_location(dockerfile):
    assert re.search(r'^ENV WINEPREFIX="?/config/\.wine"?$', dockerfile, re.MULTILINE)


def test_flattening_the_vnc_image_keeps_the_base_image_config():
    system = VNC[VNC.index("FROM scratch AS system") :]
    for needed in (
        "ENV PATH=/lsiopy/bin:",
        "ENV S6_STAGE2_HOOK=/docker-mods",
        "ENV S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0",
        "ENV VIRTUAL_ENV=/lsiopy",
        "ENV LANG=en_US.UTF-8",
        "ENV PERL5LIB=/usr/local/bin",
        "ENV PULSE_RUNTIME_PATH=/defaults",
        'ENTRYPOINT ["/init"]',
        "EXPOSE 3000 5001",
        "VOLUME /config",
        "HEALTHCHECK",
    ):
        assert needed in system, needed


def test_the_vnc_image_keeps_netcat_for_svc_kasmvnc():
    assert "netcat-openbsd" in VNC


def test_headless_exposes_only_the_api():
    assert re.findall(r"^EXPOSE (.+)$", HEADLESS, re.MULTILINE) == ["5001"]
    compose = (ROOT / "docker-compose.headless.yml").read_text()
    assert "Dockerfile.headless" in compose
    assert ":3000" not in compose


@pytest.mark.parametrize("service", ["svc-xvfb", "svc-gateway"])
def test_headless_services_are_wired_into_s6(service):
    assert (S6 / service / "type").read_text().strip() == "longrun"
    assert (S6 / service / "dependencies.d" / "init-services").exists()
    assert (S6 / "user" / "contents.d" / service).exists()
    assert (S6 / service / "run").stat().st_mode & 0o111


def test_the_gateway_service_waits_for_the_display_and_runs_as_abc():
    assert (S6 / "svc-gateway" / "dependencies.d" / "svc-xvfb").exists()
    run = (S6 / "svc-gateway" / "run").read_text()
    assert "s6-setuidgid abc /scripts/01-start.sh" in run


def test_the_gateway_finish_script_is_executable_and_stops_the_old_terminal():
    finish = S6 / "svc-gateway" / "finish"
    assert finish.stat().st_mode & 0o111
    assert "wineserver -k" in finish.read_text()


def test_the_seed_marker_survives_in_the_baked_template():
    # An older image rolled back to reseeds any volume missing this directory,
    # which would write through the links into read-only Wine files.
    assert 'mkdir -p "$drive_c/windows/mono"' in BAKE.read_text()
    seed = (ROOT / "scripts" / "03-install-mono.sh").read_text()
    assert '! -e "/config/.wine/drive_c/windows/mono"' in seed


def _link(prefix: Path, wine: Path, template: Path) -> subprocess.CompletedProcess[str]:
    script = f'source "{BAKE}"; link_builtin_dlls "{prefix}" "{wine}"'
    return subprocess.run(
        ["bash", "-c", script],
        env={"WINE_TEMPLATE": str(template), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


@pytest.fixture
def dirs(tmp_path):
    prefix, wine = tmp_path / "system32", tmp_path / "wine"
    prefix.mkdir()
    wine.mkdir()
    return prefix, wine, tmp_path


def test_an_identical_dll_becomes_a_link_to_wines_copy(dirs):
    prefix, wine, template = dirs
    (prefix / "a.dll").write_bytes(b"same")
    (wine / "a.dll").write_bytes(b"same")

    result = _link(prefix, wine, template)

    assert result.returncode == 0, result.stderr
    assert (prefix / "a.dll").is_symlink()
    assert (prefix / "a.dll").resolve() == wine / "a.dll"


def test_a_dll_an_installer_changed_is_never_replaced(dirs):
    prefix, wine, template = dirs
    (prefix / "vcruntime.dll").write_bytes(b"from the installer")
    (wine / "vcruntime.dll").write_bytes(b"from wine")

    assert _link(prefix, wine, template).returncode == 0

    assert not (prefix / "vcruntime.dll").is_symlink()
    assert (prefix / "vcruntime.dll").read_bytes() == b"from the installer"


def test_a_file_wine_does_not_ship_is_kept(dirs):
    prefix, wine, template = dirs
    (prefix / "python39.dll").write_bytes(b"python")

    assert _link(prefix, wine, template).returncode == 0

    assert (prefix / "python39.dll").read_bytes() == b"python"
    assert not (prefix / "python39.dll").is_symlink()


def test_linking_twice_changes_nothing_and_subdirectories_are_left_alone(dirs):
    prefix, wine, template = dirs
    (prefix / "a.dll").write_bytes(b"same")
    (wine / "a.dll").write_bytes(b"same")
    (prefix / "drivers").mkdir()
    (prefix / "drivers" / "x.sys").write_bytes(b"driver")

    assert _link(prefix, wine, template).returncode == 0
    assert _link(prefix, wine, template).returncode == 0

    assert (prefix / "a.dll").is_symlink()
    assert (prefix / "drivers" / "x.sys").read_bytes() == b"driver"


def test_an_empty_directory_is_not_an_error(dirs):
    prefix, wine, template = dirs
    assert _link(prefix, wine, template).returncode == 0


def test_the_bake_script_refuses_to_run_without_a_template():
    result = subprocess.run(
        ["bash", str(BAKE), "runtime"],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "WINE_TEMPLATE" in result.stderr


def test_the_bake_script_rejects_an_unknown_step(tmp_path):
    result = subprocess.run(
        ["bash", str(BAKE), "bogus"],
        env={"WINE_TEMPLATE": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr


def _verify(tmp_path: Path, fake_wine: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("wine", fake_wine), ("wineserver", "exit 0")):
        tool = bin_dir / name
        tool.write_text(f"#!/bin/bash\n{body}\n")
        tool.chmod(0o755)
    terminal = tmp_path / "mt5" / "terminal64.exe"
    terminal.parent.mkdir()
    terminal.touch()
    script = f'source "{BAKE}"; verify_terminal_starts "{terminal}"'
    return subprocess.run(
        ["bash", "-c", script],
        env={
            "WINE_TEMPLATE": str(tmp_path),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "MT5_VERIFY_SECONDS": "5",
        },
        capture_output=True,
        text=True,
    )


def test_a_terminal_stopping_on_a_dialog_fails_the_build(tmp_path):
    # MT5 build 6295 under Wine 10, 2026-11-01: installed fine, then this dialog.
    dialog = "echo 'trace:msgbox:MSGBOX_OnInit L\"A debugger has been found\"' >&2"

    result = _verify(tmp_path, dialog)

    assert result.returncode == 1
    assert "debugger has been found" in result.stderr


def test_a_terminal_that_never_writes_its_journal_fails_the_build(tmp_path):
    result = _verify(tmp_path, "exit 0")

    assert result.returncode == 1
    assert "no journal" in result.stderr


def test_a_healthy_terminal_passes_and_leaves_no_journal_behind(tmp_path):
    start = 'mkdir -p "$(dirname "$1")/logs"; touch "$(dirname "$1")/logs/20261101.log"'

    result = _verify(tmp_path, start)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "mt5" / "logs").is_dir()
    assert not list((tmp_path / "mt5" / "logs").iterdir())


def test_both_images_verify_the_terminal_unless_told_not_to():
    assert "MT5_VERIFY_TERMINAL:-1" in BAKE.read_text()
    assert "ARG MT5_VERIFY_TERMINAL=1" in VNC
    assert "ARG MT5_VERIFY_TERMINAL=1" in HEADLESS


def test_stopping_the_display_leaves_nothing_in_the_image():
    # A baked /tmp/.X99-lock named a pid alive in the next container: 2026-11-01.
    stop = BAKE.read_text().split("stop_display() {")[1].split("\n}\n")[0]
    assert '"/tmp/.X${DISPLAY#:}-lock"' in stop
    assert "/tmp/.X11-unix" in stop
    assert '"/tmp/.wine-$(id -u)"' in stop


def test_a_release_publishes_the_plain_tags_only_from_the_vnc_image():
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text()
    assert (
        "dockerfile: Dockerfile\n            suffix: ''\n            floating_tag: latest"
        in workflow
    )
    assert "dockerfile: Dockerfile.headless\n            suffix: -headless" in workflow
    assert "floating_tag: headless" in workflow


def test_the_api_waits_for_the_boot_terminal():
    # 2026-11-01: a fast restart let the API launch a terminal with no start.ini first.
    start = (ROOT / "scripts" / "01-start.sh").read_text()
    wait = start.index("terminal64")
    assert start.index("04-install-mt5.sh") < wait < start.index("05-install-python.sh")
    assert wait < start.index("waitress")
