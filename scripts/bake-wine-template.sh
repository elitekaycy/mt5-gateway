#!/bin/bash
# Bakes the Wine prefix template that scripts/03-install-mono.sh seeds into a
# fresh /config volume. Both image variants (Dockerfile, Dockerfile.headless)
# call this, so their prefixes cannot drift apart.
#
# Usage, as the runtime user (abc), with WINE_TEMPLATE set:
#   bake-wine-template.sh runtime [requirements.txt]   Wine prefix, Python, app libs
#   bake-wine-template.sh terminal                     the MT5 terminal
#
# They are separate steps so each lands in its own image layer: release builds
# rebuild only the terminal layer. What each step deletes is deleted in that step,
# because a later layer cannot reclaim bytes from an earlier one.
set -euo pipefail

WINE_TEMPLATE="${WINE_TEMPLATE:?WINE_TEMPLATE must name the template directory}"
export HOME="$WINE_TEMPLATE" WINEPREFIX="$WINE_TEMPLATE" WINEARCH=win64
export WINEDEBUG=-all WINEDLLOVERRIDES=mscoree=d DISPLAY=:99

drive_c="$WINE_TEMPLATE/drive_c"
wine_lib64="${WINE_LIB64:-/opt/wine-stable/lib64/wine/x86_64-windows}"
wine_lib32="${WINE_LIB32:-/opt/wine-stable/lib/wine/i386-windows}"
xvfb_pid=""

# The Python and MT5 installers need an X display even in silent mode, and
# `docker build` has none.
start_display() {
  local socket="/tmp/.X11-unix/X${DISPLAY#:}"
  Xvfb "$DISPLAY" -screen 0 1024x768x16 >/dev/null 2>&1 &
  xvfb_pid=$!
  for _ in $(seq 1 60); do
    [ -S "$socket" ] && return 0
    sleep 0.5
  done
  echo "bake: display $DISPLAY did not come up" >&2
  return 1
}

# Removes everything the display and Wine left in /tmp, because it would otherwise be
# baked into the image: a lock naming a pid that is alive in a later container stops
# the next X server on that display from starting.
stop_display() {
  wineserver -k 2>/dev/null || true
  if [ -n "$xvfb_pid" ]; then
    kill "$xvfb_pid" 2>/dev/null || true
    wait "$xvfb_pid" 2>/dev/null || true
    xvfb_pid=""
  fi
  rm -rf "/tmp/.X${DISPLAY#:}-lock" /tmp/.X11-unix "/tmp/.wine-$(id -u)"
}

# wineboot copies every builtin DLL into the prefix, but Wine loads builtins from
# its own lib directory. Links keep the names the prefix expects without storing
# the bytes twice in the image and again in each /config volume. A file differing
# from Wine's copy is left alone, so an installer's real DLL is never replaced.
link_builtin_dlls() {
  local prefix_dir="$1" wine_dir="$2" file builtin
  for file in "$prefix_dir"/*; do
    builtin="$wine_dir/$(basename "$file")"
    if [ -f "$file" ] && [ ! -L "$file" ] && [ -f "$builtin" ] && cmp -s "$file" "$builtin"; then
      ln -sf "$builtin" "$file"
    fi
  done
}

# The installer succeeding proves nothing about the terminal running: MT5 build 6295
# installs fine, then its protection stops it under Wine 10 with a "debugger has been
# found" dialog that nobody can see on a virtual display. So start it, and fail the
# build if it shows a dialog or never writes its journal.
verify_terminal_starts() {
  local terminal="$1" seconds="${MT5_VERIFY_SECONDS:-120}"
  local logs output dialog
  logs="$(dirname "$terminal")/logs"
  output="$(mktemp)"
  WINEDEBUG=+msgbox timeout "$seconds" wine "$terminal" >"$output" 2>&1 || true
  wineserver -k 2>/dev/null || true
  dialog="$(grep -m1 -o 'MSGBOX_OnInit.*' "$output" || true)"
  if [ -n "$dialog" ]; then
    echo "mt5 install: FAILED, the terminal stopped with a dialog: $dialog" >&2
    rm -f "$output"
    return 1
  fi
  if ! find "$logs" -type f 2>/dev/null | grep -q .; then
    echo "mt5 install: FAILED, the terminal wrote no journal (limit ${seconds}s). Wine said:" >&2
    tail -n 10 "$output" >&2
    rm -f "$output"
    return 1
  fi
  rm -f "$output"
  # The check's own journal has no place in the template.
  find "$logs" -type f -delete
  echo "mt5 install: terminal started and wrote its journal"
}

bake_runtime() {
  local requirements="${1:-/tmp/requirements.txt}"
  local python_sha256=fb3d0466f3754752ca7fd839a09ffe53375ff2c981279fd4bc23a005458f7f5d

  start_display
  trap stop_display EXIT
  wineboot -i
  wineserver -w

  wget -qO /tmp/python.exe https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe
  printf '%s  %s\n' "$python_sha256" /tmp/python.exe | sha256sum -c -
  wine /tmp/python.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 \
    Include_doc=0 Include_tcltk=0 Include_dev=0 Include_launcher=0 Include_tools=0
  wineserver -w
  wine python -m pip install --no-cache-dir --upgrade pip 'setuptools>=78.1.1'
  wineserver -w
  wine python -m pip install --no-cache-dir -r "$requirements"
  wineserver -w
  stop_display
  trap - EXIT

  rm -f /tmp/python.exe
  rm -rf "$drive_c/users/abc/AppData/Local/pip" \
    "$drive_c/ProgramData/Package Cache"
  find "$drive_c/windows/Installer" -mindepth 1 -delete

  # Nothing here runs .NET, so Mono is not installed. The empty directory stays:
  # 03-install-mono.sh, in this image and in any older one rolled back to, reads
  # it as "this volume is seeded". An older image seeing it missing would copy its
  # own template over this prefix.
  mkdir -p "$drive_c/windows/mono"

  link_builtin_dlls "$drive_c/windows/system32" "$wine_lib64"
  link_builtin_dlls "$drive_c/windows/syswow64" "$wine_lib32"
}

bake_terminal() {
  # Normally copies the pinned terminal in MT5_TERMINAL_SOURCE. With that empty it runs
  # the MetaQuotes web installer, which always fetches the newest build. It can spin
  # forever under Wine and exits non-zero even on a good install, so only terminal64.exe
  # existing decides success. MetaQuotes rotates the stub: re-pin MT5_SETUP_SHA256 in both
  # Dockerfiles and mt5setup_sha256 in scripts/02-common.sh together.
  local mt5_dir="$drive_c/Program Files/MetaTrader 5"
  local terminal="$mt5_dir/terminal64.exe"
  local attempt=0 status=0 note source_note

  start_display
  trap stop_display EXIT
  wine reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f
  if [ -n "${MT5_TERMINAL_SOURCE:-}" ]; then
    mkdir -p "$mt5_dir"
    cp -r --preserve=timestamps "$MT5_TERMINAL_SOURCE/." "$mt5_dir/"
    source_note="$MT5_TERMINAL_SOURCE"
  else
    wget -qO /tmp/mt5setup.exe "$MT5_SETUP_URL"
    printf '%s  %s\n' "$MT5_SETUP_SHA256" /tmp/mt5setup.exe | sha256sum -c -
    source_note="$MT5_SETUP_URL"
    echo "mt5 install: build space before install: $(df -Pk "$WINE_TEMPLATE" | awk 'NR==2 {print $4 " KiB free on " $6}')"
    while [ ! -f "$terminal" ] && [ "$attempt" -lt 3 ]; do
      attempt=$((attempt + 1))
      status=0
      timeout 600 wine /tmp/mt5setup.exe /auto || status=$?
      case "$status" in
        0) note="clean exit" ;;
        124) note="killed by the 600s timeout" ;;
        *) note="non-zero exit; the MT5 installer does this even on a good install, so the terminal check below decides" ;;
      esac
      echo "mt5 install: attempt $attempt: exit=$status ($note)"
      [ -f "$terminal" ] || wineserver -k || true
    done
  fi
  if [ ! -f "$terminal" ]; then
    echo "mt5 install: FAILED after $attempt attempt(s), last exit=$status; no terminal64.exe" >&2
    echo "mt5 install: space now: $(df -Pk "$WINE_TEMPLATE" | awk 'NR==2 {print $4 " KiB free on " $6}')" >&2
    echo "mt5 install: a starved build filesystem is the usual cause; several GiB are needed here" >&2
    exit 1
  fi
  echo "mt5 install: terminal64.exe present from $source_note"
  printf 'terminal_source=%s\ninstalled_at=%s\nterminal_build=%s\n' \
    "$source_note" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(python3 /scripts/mt5-terminal-build.py "$terminal")" \
    >"$WINE_TEMPLATE/.mt5-install-info"
  # The gateway only runs terminal64.exe. The bundled history is sample data; the
  # terminal syncs real history from the logged-in broker.
  wineserver -k 2>/dev/null || true
  rm -f /tmp/mt5setup.exe "$mt5_dir/MetaEditor64.exe" "$mt5_dir/metatester64.exe" \
    "$mt5_dir/uninstall.exe"
  rm -rf "$mt5_dir/Bases/Default/History" \
    "$drive_c/users/abc/AppData/Roaming/MetaQuotes/WebInstall"

  if [ "${MT5_VERIFY_TERMINAL:-1}" != "0" ]; then
    verify_terminal_starts "$terminal"
  fi
  stop_display
  trap - EXIT
}

main() {
  case "${1:-}" in
    runtime)
      shift
      bake_runtime "$@"
      ;;
    terminal) bake_terminal ;;
    *)
      echo "usage: $0 runtime [requirements.txt] | terminal" >&2
      exit 2
      ;;
  esac
}

# Sourcing defines the functions without running anything, for the unit tests.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
