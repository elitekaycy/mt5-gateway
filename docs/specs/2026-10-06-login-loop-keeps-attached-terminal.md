# The boot login loop never kills the terminal the API is attached to

Related: bot2 forward-stack outage 2026-10-06 (terminal build 6230).

## Problem

On 2026-10-06 the Exness terminal on bot2 self-updated from build 6182 to 6230.
From then on, every gateway boot took the API down within seconds of it coming
up and kept it down for about eleven minutes. With qkt polling, the outage did
not end until the container was restarted.

The terminal journal (`logs/20261006.log`), `/var/log/mt5_setup.log` and the
gateway log give this sequence for the 13:25 boot:

| UTC | Source | Event |
|---|---|---|
| 13:25:26 | setup log | Login attempt via `13.247.140.197:443` (first window 36 x 5 s) |
| 13:28:24 | journal | Account authorized (reported later as "previous successful authorization ... 13:28:24") |
| 13:28:26 | gateway | `MT5 initialized successfully`, account 476422618 |
| 13:28:39 | setup log | `No authorization via '13.247.140.197:443'` -> `pkill -f terminal64.exe` |
| 13:28:39.956 | gateway | `MT5 IPC failure: (-10001, 'IPC send failed')` |
| 13:28:45 | journal | Terminal started without the boot ini (launched by `mt5.initialize()`) |
| 13:28:48 | journal | The loop's next candidate: `terminal process already started`, exit 0 |
| ... | | Repeats for each of the 6 candidates, about every 95 s |
| 13:36:45 | setup log | `No candidate authorized; leaving terminal retrying` |
| 13:37:39 | journal | That terminal authorizes; the API reconnects at 13:37:41 |

Three defects combine:

1. **The loop trusts only the journal.** `authorized()` counts `authorized on`
   lines. On build 6230 the first login after a cold boot took 178 s against a
   180 s window, and the line was not on disk when the window closed. The loop
   then killed a terminal that was logged in, with the API attached to it.
   On build 6182 the same boot authorized in about 35 s, so the kill never ran.
2. **A reconnect relaunches a terminal that cannot log in.** After the kill,
   the API's `mt5.initialize()` finds no terminal and starts one
   (`terminal64.exe /portable`) without credentials. That terminal never
   authorizes: it never did in 69 minutes on bot2 (12:16-13:25), and never did
   on a local build 6230 demo. Every later `initialize()` returns IPC timeout
   -10005. Because it starts first, it also holds the terminal's single-instance
   lock, so the loop's credentialed launch exits with `terminal process already
   started`.
3. **Every request starts a reconnect.** After a failed reconnect cycle, the
   next request starts another one. Under qkt's poll load this happens
   continuously, so the API's uncredentialed relaunch reliably wins the race
   against the loop's final launch, and the outage outlives the loop.

The load from 15 strategies was not the cause. With the terminal left alone,
the same gateway served the full qkt warmup at once, and a local build 6230
gateway served 107-114 req/s of mixed tick, rate, account and position calls.

## Behaviour

- After every successful attach, the API writes `/tmp/mt5-api-session` with
  `<login> <epoch>` (`Z:\tmp\...` from Wine). The loop counts a candidate as
  authorized when the journal count rises **or** that marker names `MT5_LOGIN`
  with a time at or after the candidate's launch. It checks once more before
  any `pkill`. The boot clears the marker first, so a previous boot's marker
  cannot count.
- The loop records the candidate that authorized in `/tmp/mt5-login-server`.
- A reconnect (not the boot attach) calls `mt5.initialize(login=, password=,
  server=)` with env-login credentials, using the recorded address or else
  `MT5_SERVER`. A terminal the API has to relaunch then logs in. The boot attach
  still passes no credentials, so it never races the loop's ini login.
- A failed reconnect starts a back-off window of `MT5_RECONNECT_COOLDOWN_SECONDS`
  (default 5), doubling per consecutive failure up to
  `MT5_RECONNECT_COOLDOWN_MAX_SECONDS` (default 60). Requests inside the window
  fail fast with 503 and do not call `initialize()`. A successful reconnect
  clears the window.
- `MT5_LOGIN_FIRST_TRIES` (default 36) and `MT5_LOGIN_TRIES` (default 18) set
  the loop's 5-second polls per candidate.

## Verification

- Unit: `tests/test_reconnect_relaunch.py` (credentials on reconnect, none on
  boot attach, marker written, back-off and its reset) and the marker and
  credential helpers in `tests/test_autologin.py`. Four of the six reconnect
  tests fail on the previous `mt5_connection.py`.
- Local demo (build 6230), files hot-loaded into the 0.3.17 container:
  - Cold boot: the first candidate authorized, the marker and login-server file
    were written, and nothing was killed.
  - `kill` of the terminal: the API relaunched it with credentials and served
    `/account` again 10 s later. Without the fix, the relaunched terminal
    stayed logged out and every call returned -10005.
  - Kill under a 16-worker load (107 req/s): 2 of 9,636 requests failed with
    503, the slowest took 7.3 s, then the load continued normally.
