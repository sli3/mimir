---
description: >
  Manual frontend review, independent of /build. Starts the Vite dev server
  if needed, invokes @frontend-reviewer, then tears down cleanly. This is the
  designated fallback for when /build's Step 6B fails to start the dev server
  — /build continues and completes without blocking on that failure, and its
  Step 10 report will tell you to run this command afterward. Also usable
  standalone at any time you want a frontend review outside a full build.
agent: build
subtask: false
---

You are managing the Vite dev server lifecycle around a frontend review.
Follow these steps exactly, in order. Do not skip the readiness check or the
teardown check — both are required every time this command runs.

## Step 1 — Check if the dev server is already running

Run:
```
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ --max-time 2
```

- If the output is `200`, the dev server is ALREADY RUNNING. Set an internal
  flag `server_already_running = true`. Skip to Step 3.
- If the command fails, times out, or returns anything other than `200`, the
  dev server is NOT running. Set `server_already_running = false`. Continue to
  Step 2.

## Step 2 — Start the dev server and wait for readiness

Start it in the background:
```
nohup npm run dev --prefix dashboard/frontend > /tmp/mimir-vite-dev.log 2>&1 &
```

Poll for readiness every 2 seconds, for a MAXIMUM of 12 attempts (24 seconds
total — Vite dev servers on this project typically start in 2-5 seconds, so
24 seconds is a generous ceiling, not an expected wait):

```
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ --max-time 2
```

- As soon as this returns `200`, the server is ready. Proceed to Step 3.
- If all 12 attempts return anything other than `200` (24 seconds elapsed),
  go to Step 4 for teardown first (the start attempt may still be running
  in the background even though it never became ready), then report to the
  user: "Vite dev server failed to start within 24 seconds. Check
  /tmp/mimir-vite-dev.log for errors." Print the last 20 lines of that log
  and end here — do not proceed to Step 3.

## Step 3 — Invoke frontend-reviewer

Only reached if the server responded with `200` (either it was already
running, or it just started successfully).

Invoke @frontend-reviewer with the following task: $ARGUMENTS

Wait for its full report before continuing to Step 4.

## Step 4 — Teardown (mandatory, run every time)

Check the internal flag from Step 1:

- If `server_already_running = true`: do NOT stop anything. The server was
  running before this command started and may be in use elsewhere. Skip
  teardown entirely and just present the frontend-reviewer's report.

- If `server_already_running = false` (we attempted to start it in Step 2,
  whether or not it became ready): stop whatever process is bound to port
  5173. Do NOT track this by the `nohup` command's own PID — `npm run dev`
  spawns Vite as a child process, and killing the `npm` wrapper's PID does
  not reliably terminate that child, leaving an orphaned dev server on the
  port. Target the port directly instead:
  ```
  lsof -ti:5173 | xargs -r kill
  ```
  Wait 2 seconds, then confirm it actually stopped:
  ```
  curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ --max-time 2
  ```
  If this still returns `200`, escalate once with a stronger signal, still
  scoped to the same port (never broaden to a name-based `pkill`, which
  risks killing an unrelated process on this machine):
  ```
  lsof -ti:5173 | xargs -r kill -9
  ```
  Confirm again. If port 5173 is still responding after both attempts,
  report that the dev server needs manual cleanup — do not attempt further
  kills. (Requires `lsof` — standard on Fedora Workstation.)

## Final report to the user

Present, in this order:
1. Whether you started the dev server yourself, or it was already running
2. @frontend-reviewer's full findings (or, if Step 2 timed out, the log tail
   and failure notice instead)
3. Whether teardown ran, and its outcome (stopped cleanly / not needed /
   needs manual cleanup)
