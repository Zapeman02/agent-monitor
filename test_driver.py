import json, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LOG = os.path.join(tempfile.mkdtemp(), "stdin.log")
os.environ.update(AM_CLAUDE=os.path.join(HERE, "tests", "fake_claude.py"), AM_FAKE_STDIN_LOG=LOG, AM_FAKE_DELAY="0")
import driver

FX = os.path.join(HERE, "tests", "fixtures")
tmp = tempfile.mkdtemp()


def until(f, what, t=10):
    end = time.time() + t
    while time.time() < end:
        if (r := f()): return r
        time.sleep(0.02)
    raise AssertionError("timeout: " + what)


def has(s, pred): return any(pred(e) for e in s.snapshot())


def pid_gone(pid):
    try: os.kill(pid, 0)
    except ProcessLookupError: return True
    return False


# validation
for kw in ({"mode": "bypassPermissions"}, {"resume": "../x"}, {"resume": "nope"}):
    try: driver.Session(tmp, **kw); raise SystemExit(f"accepted {kw}")
    except ValueError: pass
for bad in (os.path.join(tmp, "nope"), os.path.join(tmp, "f")):
    open(os.path.join(tmp, "f"), "w").close()
    try: driver.Session(bad); raise SystemExit("bad cwd accepted")
    except ValueError: pass
assert not os.path.exists(LOG) and not driver.SESSIONS

# allow path
s = driver.Session(tmp, "plan")
assert "--bare" not in s.argv and s.argv[s.argv.index("--permission-mode") + 1] == "plan" and "--resume" not in s.argv
s.prompt("/cdt:orchestration hej")
until(lambda: s.sid == "00a9be51-d8e3-4c86-a657-3e6dfb152646", "sid")
rid = next(iter(until(lambda: dict(s.pending), "pending")))
assert not has(s, lambda e: e.get("type") == "result")
try: s.set_mode("bypassPermissions"); raise SystemExit("bad mode accepted")
except ValueError: pass
assert s.status == "waiting"
s.answer(rid, True)
until(lambda: has(s, lambda e: e.get("type") == "result"), "result")
assert not s.pending and has(s, lambda e: e.get("subtype") == "task_started") and has(s, lambda e: e.get("subtype") == "task_notification")
try: s.answer(rid, True); raise SystemExit("double answer")
except KeyError: pass
s.set_mode("acceptEdits")
until(lambda: "set_permission_mode" in open(LOG).read(), "fake logged mode")
lines = [json.loads(l) for l in open(LOG)]
users = [l for l in lines if l.get("type") == "user"]
assert users[0]["message"]["content"] == "/cdt:orchestration hej" and lines[0]["request"]["subtype"] == "initialize"
assert any(l["request"]["subtype"] == "set_permission_mode" for l in lines if l.get("type") == "control_request" and l["request"]["subtype"] != "initialize")
time.sleep(0.3); evs = s.snapshot()
assert s.wait(len(evs), 0.1) == [] and s.batch(0, 0)[0] == 0
pid = s.proc.pid
s.close()
until(lambda: pid_gone(pid), "child gone")
until(lambda: s.events[-1]["type"] == "am_exit" and s.events[-1]["code"] == 0, "am_exit")
try: s.prompt("x"); raise SystemExit("prompt after exit")
except RuntimeError: pass

assert s.snapshot()[0] == {"type": "user", "am_local": True, "message": {"role": "user", "content": "/cdt:orchestration hej"}, "parent_tool_use_id": None}
import graph; graph.reduce(s.snapshot(), None)   # string-content local prompt is tolerated

# deny path
os.environ["AM_FAKE_FIXTURE"] = os.path.join(FX, "stream-deny.jsonl")
s = driver.Session(tmp); s.prompt("go")
rid = next(iter(until(lambda: dict(s.pending), "pending")))
s.answer(rid, False)
until(lambda: has(s, lambda e: e.get("type") == "result"), "result")
assert has(s, lambda e: e.get("type") == "user" and "Denied" in json.dumps(e) and '"is_error": true' in json.dumps(e))
assert has(s, lambda e: e.get("type") == "am_answered" and e["behavior"] == "deny")
s.close()

# interrupt
s = driver.Session(tmp); s.prompt("go")
until(lambda: s.pending, "pending")
s.interrupt()
until(lambda: has(s, lambda e: e.get("subtype") == "error_during_execution"), "interrupted")
assert s.alive()
s.close()

# cap: 8 live
os.environ["AM_FAKE_FIXTURE"] = os.path.join(FX, "stream-recording.jsonl")
ss = [driver.Session(tmp) for _ in range(8)]
try: driver.Session(tmp); raise SystemExit("9th accepted")
except driver.TooMany: pass
pids = [x.proc.pid for x in ss]
for x in ss: x.close()
assert all(pid_gone(p) for p in pids)

# "~" cwd is expanded; claude missing -> NoClaude
os.environ["HOME"] = tmp; os.makedirs(os.path.join(tmp, "rel"), exist_ok=True)
s = driver.Session("~/rel"); assert s.cwd == os.path.realpath(os.path.join(tmp, "rel")); s.close()
real = driver.CLAUDE; driver.CLAUDE = None
try: driver.Session(tmp); raise SystemExit("no claude accepted")
except driver.NoClaude: pass
driver.CLAUDE = real

# resume is validated; only the 8 newest ended sessions are kept
try: driver.Session(tmp, resume="../../etc/passwd"); raise SystemExit("bad resume")
except ValueError: pass
for _ in range(11):
    x = driver.Session(tmp); x.close(); until(lambda: not x.alive(), "ended")
driver.Session(tmp).close()
assert len([x for x in driver.SESSIONS.values() if not x.alive()]) <= 9 and len(driver.SESSIONS) <= 9

# event cap keeps indices monotonic
driver.MAX_EVENTS = 5
s = driver.Session(tmp)
for i in range(12): s._append({"type": "x", "i": i})
start, evs = s.batch(0, 0)
assert start == s.base and s.base + len(s.events) >= 12 and evs[-1]["i"] == 11 and len(evs) == 5
s.close()
print("ok")
