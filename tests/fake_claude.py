#!/usr/bin/env python3
"""Fake `claude -p` for tests: replays a stream-json fixture. Env: AM_FAKE_FIXTURE, AM_FAKE_DELAY, AM_FAKE_STDIN_LOG."""
import json, os, queue, sys, threading

if any(a in ("--bare", "--dangerously-skip-permissions", "--setting-sources", "bypassPermissions") for a in sys.argv):
    sys.exit(2)
HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.environ.get("AM_FAKE_FIXTURE") or os.path.join(HERE, "fixtures", "stream-recording.jsonl")
DELAY = float(os.environ.get("AM_FAKE_DELAY", "0.02"))
LOG = os.environ.get("AM_FAKE_STDIN_LOG")
q = queue.Queue()


def pump():
    for line in sys.stdin:
        if LOG:
            with open(LOG, "a") as f: f.write(line if line.endswith("\n") else line + "\n")
        try: q.put(json.loads(line))
        except ValueError: pass
    q.put(None)


def out(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()


def ok(rid, resp=None):
    out({"type": "control_response", "response": {"subtype": "success", "request_id": rid, "response": resp or {}}})


def result(sub="success"):
    out({"type": "result", "subtype": sub, "is_error": sub != "success", "session_id": sid})


def common(m):
    """Handle messages valid at any time. Returns 'interrupt' if the replay must stop."""
    r = m.get("request") or {}
    if m.get("type") == "control_request":
        if r.get("subtype") == "interrupt":
            ok(m["request_id"], {"still_queued": []}); result("error_during_execution"); return "interrupt"
        ok(m["request_id"])


threading.Thread(target=pump, daemon=True).start()
lines = [json.loads(l) for l in open(FIX) if l.strip()]
init = next(d for d in lines if d.get("type") == "control_response")
sid = next((d.get("session_id") for d in lines if d.get("session_id")), "00000000-0000-0000-0000-000000000000")
first_user = False
while True:                     # handshake, then wait for the first user message
    m = q.get()
    if m is None: sys.exit(0)
    if (m.get("request") or {}).get("subtype") == "initialize":
        init["response"]["request_id"] = m["request_id"]; out(init)
    elif m.get("type") == "user": break
    else: common(m)

stopped = False
for d in lines:
    if d is init or stopped: continue
    try: m = q.get(timeout=DELAY)
    except queue.Empty: m = False
    if m is None: sys.exit(0)
    if m and common(m) == "interrupt": break
    out(d)
    if d.get("type") == "control_request" and d["request"].get("subtype") == "can_use_tool":
        while True:             # block until the host answers this request
            m = q.get()
            if m is None: sys.exit(0)
            resp = m.get("response") or {}
            if m.get("type") == "control_response" and resp.get("request_id") == d["request_id"]:
                if (resp.get("response") or {}).get("behavior") == "deny":
                    out({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result",
                         "tool_use_id": d["request"].get("tool_use_id"), "content": "Denied in Agent Monitor", "is_error": True}]},
                         "parent_tool_use_id": None, "session_id": sid})
                    result(); stopped = True
                break
            if common(m) == "interrupt": stopped = True; break
        if stopped: break

while True:                     # idle: further turns
    m = q.get()
    if m is None: sys.exit(0)
    if m.get("type") == "user":
        out({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}, "parent_tool_use_id": None, "session_id": sid})
        result()
    else: common(m)
