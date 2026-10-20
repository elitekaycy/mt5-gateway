# A container restarted with its host clears the X lock of the previous boot

Related: hg20k outage on bot1, 2026-10-18 13:51Z to 2026-10-20 14:54Z.

## Problem

A container restarted after an unclean stop (a host reboot) keeps its `/tmp`, including
`/tmp/.X0-lock` from the Xvnc of the previous boot. X treats a lock as live while the pid in it
exists. On bot1 the lock (written 2026-10-06) named pid 206, which after the reboot was nginx, so
every Xvnc start failed with `Server is already active for display 0`. Without a display there was
no terminal and no API on :5001, and qkt crash-looped for two days (2,796 restarts).

A graceful stop does not leave the lock (Xvnc removes it), so ordinary restarts never showed this.

## Behaviour

`root/custom-cont-init.d/10-clear-stale-x-lock` runs at container start through the base image's
`init-custom-files`, which `svc-kasmvnc` waits for. No X server can be running then, so the script
removes every `/tmp/.X*-lock` and its `/tmp/.X11-unix/X<n>` socket and logs the display and pid.

## Proof

`tests/test_stale_x_lock.py` covers the script. Image check on 0.3.19: kill the container, copy in
a lock naming pid 1, start it. Without the script Xvnc never starts (40 `already active` errors in
40 s); with it the lock is removed and Xvnc runs.
