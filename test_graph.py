import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import graph

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures")
load = lambda n: [json.loads(l) for l in open(os.path.join(FX, n))]
byid = lambda g: {n["id"]: n for n in g["nodes"]}

# empty
g = graph.reduce([])
assert [n["id"] for n in g["nodes"]] == ["lead"] and g["edges"] == [] and g["waves"] == [] and g["permissions"] == []
assert graph.reduce([{"type": "wat"}, 5, {"type": "assistant"}, {"type": "system", "subtype": "task_progress"}], {"phases": 3})["nodes"]

# allow recording
ev = load("stream-recording.jsonl")
phase = {"phases": [{"name": "Build", "status": "running", "agents": ["general-purpose"]}]}
TU = "toolu_01GmmQWBVtL4w9xyMg85ZFFo"
i_req = next(i for i, e in enumerate(ev) if e["type"] == "control_request")
mid = graph.reduce(ev[:i_req + 1], phase)
a = byid(mid)[TU]
assert a["status"] == "waiting" and a["agent_id"] == "aa0949f82fdc2a041" and a["tokens"] == 24073 and a["wave"] == 0
assert len(mid["permissions"]) == 1 and mid["permissions"][0]["node"] == TU and mid["session"]["status"] == "waiting"
assert not [e for e in mid["edges"] if e["kind"] == "handback"]
g = graph.reduce(ev, phase)
agents = [n for n in g["nodes"] if n["kind"] == "agent"]
assert len(agents) == 1 and agents[0]["status"] == "done" and agents[0]["tokens"] == 31811 and agents[0]["wave"] == 0
assert [e["id"] for e in g["edges"]] == ["d:" + TU, "h:" + TU] and g["edges"][1]["label"].startswith("DONE")
assert g["permissions"] == [] and g["session"]["status"] == "idle" and g["session"]["cost_usd"] > 0
assert g["waves"] == [{"index": 0, "name": "Build", "status": "running", "agents": ["general-purpose"]}]
assert graph.reduce(ev, {"junk": 1})["waves"] == [] and graph.reduce(ev, None)["nodes"][1]["wave"] is None
assert graph.reduce(ev[:i_req + 1] + [{"type": "am_answered", "request_id": mid["permissions"][0]["request_id"]}])["permissions"] == []

# deny recording
ev = load("stream-deny.jsonl")
g = graph.reduce(ev[:next(i for i, e in enumerate(ev) if e["type"] == "control_request") + 1])
assert [n["kind"] for n in g["nodes"]] == ["lead"] and g["nodes"][0]["status"] == "waiting"
assert len(g["permissions"]) == 1 and g["permissions"][0]["node"] == "lead" and g["permissions"][0]["tool_name"] == "Bash"

# T2 transcript fixture
sj = os.path.join(FX, "t2", "cb492573-7564-46f0-ab1d-df4568c13342.jsonl")
phase = json.load(open(os.path.join(FX, "t2", "phase.json")))
g = graph.reduce(graph.events_from_transcript(sj), phase)
assert next(n for n in g["nodes"] if n["id"] == "lead")["tokens"] > 0   # lead usage is counted too
agents = [n for n in g["nodes"] if n["kind"] == "agent"]
assert sorted(n["agent_type"].split(":")[-1] for n in agents) == [
    "backend-engineer", "code-reviewer", "frontend-engineer", "mobile-engineer", "security-reviewer"]
assert sorted(e["kind"] for e in g["edges"]) == ["dispatch"] * 5 + ["handback"] * 5
assert all(n["status"] == "done" and n["tools"] > 0 and n["tokens"] > 0 and n["background"] for n in agents)
assert {n["wave"] for n in agents if "engineer" in n["agent_type"] and "security" not in n["agent_type"]} == {0}
assert all(n["wave"] == 1 for n in agents if "reviewer" in n["agent_type"])
# a dispatch-time-only transcript (no notifications) must leave every agent running: "Async agent launched" is no handback
evs = [e for e in graph.events_from_transcript(sj) if not (e.get("subtype") == "task_notification")]
g2 = graph.reduce(evs)
assert not [e for e in g2["edges"] if e["kind"] == "handback"]
assert all(n["status"] == "running" for n in g2["nodes"] if n["kind"] == "agent")

# early notifications outside the tail window are still found (whole-file scan)
g3 = graph.reduce(graph.events_from_transcript(sj, max_bytes=3000), phase)
assert [n["status"] for n in g3["nodes"] if n["kind"] == "agent"] == ["done"] * 5
assert len([e for e in g3["edges"] if e["kind"] == "dispatch"]) == 5   # early dispatches outside the tail are found too
# unknown-node notification creates no orphan
g4 = graph.reduce([{"type": "system", "subtype": "task_notification", "task_id": "zz", "tool_use_id": "nope", "status": "completed"}])
assert [n["id"] for n in g4["nodes"]] == ["lead"]

# nesting: a subagent's own Agent call is a child of that subagent
nest = [
    {"type": "assistant", "message": {"id": "m1", "content": [{"type": "tool_use", "id": "X", "name": "Agent", "input": {"subagent_type": "a"}}]}},
    {"type": "assistant", "parent_tool_use_id": "X", "message": {"id": "m2", "content": [{"type": "tool_use", "id": "Y", "name": "Agent", "input": {"subagent_type": "b"}}]}},
]
g5 = graph.reduce(nest)
assert byid(g5)["Y"]["parent"] == "X" and byid(g5)["X"]["parent"] == "lead"
assert [e for e in g5["edges"] if e["id"] == "d:Y"][0]["source"] == "X"

# wave assigned at dispatch time from cdt-phase calls
def _bash(i, cmd):
    return {"type": "assistant", "message": {"id": "b" + i, "content": [{"type": "tool_use", "id": "B" + i, "name": "Bash", "input": {"command": cmd}}]}}
def _disp(i):
    return {"type": "assistant", "message": {"id": "d" + i, "content": [{"type": "tool_use", "id": "D" + i, "name": "Agent", "input": {"subagent_type": "cdt:backend-engineer"}}]}}
ph = {"phases": [{"name": "M0 · Plan", "status": "done", "agents": []}, {"name": "M3 · Build", "status": "running", "agents": ["backend-engineer"]}]}
evs = [_bash("1", 'cdt-phase "M1  ·  Build" --agents backend-engineer'), _disp("1"),
       _bash("2", "cdt-phase 'M3 · Build' --agents x"), _disp("2"), _bash("3", "cdt-phase done"),
       _bash("4", "x && cdt-phase Review --agents y"), _disp("3")]
g6 = graph.reduce(evs, ph)
assert [byid(g6)[k]["wave"] for k in ("D1", "D2", "D3")] == [2, 1, 3]
assert [(w["name"], w["status"]) for w in g6["waves"]] == [("M0 · Plan", "done"), ("M3 · Build", "running"), ("M1 · Build", "done"), ("Review", "running")]
assert byid(graph.reduce([_disp("1")], ph))["D1"]["wave"] == 1   # no cdt-phase call: phase.json fallback

# cdt-phase must be the command, not an argument / pipe target / heredoc text
for cmd in ("rg cdt-phase x", "echo cdt-phase | wc", "cat <<'EOF'\n# cdt-phase calls\nEOF", "cdt-phase done", "cdt-phase --agents a"):
    assert graph._phase_name(cmd) is None, cmd
assert graph._phase_name('cd x && ~/.claude/bin/cdt-phase "M1 · Build" --agents a,b 2>&1 | tail -2') == "M1 · Build"
assert graph._phase_name("echo hi\n/home/x/.claude/bin/cdt-phase Review") == "Review"

# lead totals are whole-file, independent of the tail window
lt = lambda g: {k: next(n for n in g["nodes"] if n["id"] == "lead")[k] for k in ("tokens", "tools")}
assert lt(graph.reduce(graph.events_from_transcript(sj, max_bytes=3000))) == lt(graph.reduce(graph.events_from_transcript(sj))) and lt(g)["tools"] > 0

# node_log
lead = graph.node_log(sj, "lead")
assert lead and {"ts", "role", "text"} <= set(lead[0]) and len(graph.node_log(sj, "lead", limit=3)) == 3
one = agents[0]["agent_id"]
log = graph.node_log(sj, one)
assert log and all(len(e["text"]) <= 4000 for e in log) and any(e["role"] == "tool_use" and e["tool"] for e in log)
assert graph.node_log(sj, "nope") == []
for bad in ("../x", "a/b", "", "x" * 65, "a\n"):
    try:
        graph.node_log(sj, bad)
        raise SystemExit("expected ValueError for %r" % bad)
    except ValueError:
        pass
print("ok")
