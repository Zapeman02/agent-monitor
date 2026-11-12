#!/usr/bin/env python3
"""Build tests/fixtures/t2/ : a structural, scrubbed copy of a real CDT transcript (+ subagents/).
Keeps ids, timestamps, models, usage, tool names, agent types; replaces all free text with "text#N".
Agent descriptions become generic "<agent_type> task N".
Usage: make_fixture.py <source_session.jsonl>   (a real CDT session with subagents/ beside it)"""
import json, os, re, shutil, sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "t2")
USAGE = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
n = 0
DESC = {}   # real description -> generic one, so tool_use and meta stay consistent


def desc(real, atype):
    return DESC.setdefault(real, f"{(atype or 'agent').split(':')[-1]} task {len(DESC) + 1}")


def txt(prefix=""):
    global n
    n += 1
    return f"{prefix}text#{n}"


def block(x):
    t = x.get("type")
    if t == "text":
        return {"type": "text", "text": txt()}
    if t == "tool_use":
        inp = x.get("input") or {}
        if x.get("name") in ("Agent", "Task"):
            keep = {k: inp.get(k) for k in ("subagent_type", "run_in_background") if k in inp}
            keep["description"] = desc(inp.get("description"), inp.get("subagent_type"))
        else:
            keep = {"arg": txt()}
        return {"type": "tool_use", "id": x.get("id"), "name": x.get("name"), "input": keep}
    if t == "tool_result":
        c = x.get("content")
        s = c if isinstance(c, str) else " ".join(i.get("text", "") for i in c or [] if isinstance(i, dict))
        pre = "Async agent launched successfully. " if s.startswith("Async agent launched") else ""
        return {"type": "tool_result", "tool_use_id": x.get("tool_use_id"), "is_error": bool(x.get("is_error")),
                "content": [{"type": "text", "text": txt(pre)}]}
    return None


def entry(d):
    t = d.get("type")
    base = {k: d[k] for k in ("type", "timestamp", "uuid", "parentUuid", "sessionId", "agentId", "isSidechain") if k in d}
    if t == "queue-operation":
        base["operation"] = d.get("operation")
        c = d.get("content")
        if isinstance(c, str) and "<task-notification>" in c:
            f = {k: (re.search(f"<{k}>(.*?)</{k}>", c, re.S) or [None, ""])[1] for k in ("task-id", "tool-use-id", "status")}
            base["content"] = ("<task-notification>\n<task-id>%(task-id)s</task-id>\n<tool-use-id>%(tool-use-id)s</tool-use-id>\n"
                               "<status>%(status)s</status>\n<summary>" % f) + txt() + "</summary>\n</task-notification>"
        elif c:
            base["content"] = txt()
        return base
    if t not in ("assistant", "user"):
        return None
    base["cwd"] = "/fixture/project"
    m = d.get("message") or {}
    c = m.get("content")
    blocks = [txt()] if isinstance(c, str) else [b for b in map(block, [i for i in c or [] if isinstance(i, dict)]) if b]
    msg = {"role": m.get("role"), "content": blocks[0] if isinstance(c, str) else blocks}
    if t == "assistant":
        msg.update(id=m.get("id"), model=m.get("model"), stop_reason=m.get("stop_reason"),
                   usage={k: (m.get("usage") or {}).get(k, 0) for k in USAGE})
    base["message"] = msg
    return base


def jsonl(src, dst):
    with open(src) as f, open(dst, "w") as o:
        for l in f:
            try:
                e = entry(json.loads(l))
            except Exception:
                continue
            if e:
                o.write(json.dumps(e) + "\n")


def main(src):
    sid = os.path.splitext(os.path.basename(src))[0]
    shutil.rmtree(OUT, ignore_errors=True)
    sub = os.path.join(OUT, sid, "subagents")
    os.makedirs(sub)
    jsonl(src, os.path.join(OUT, sid + ".jsonl"))
    for jl in os.listdir(os.path.join(os.path.dirname(src), sid, "subagents")):
        p = os.path.join(os.path.dirname(src), sid, "subagents", jl)
        if jl.endswith(".meta.json"):
            m = json.load(open(p))
            json.dump({**{k: m[k] for k in ("agentType", "toolUseId", "spawnDepth", "requestShape") if k in m},
                       "description": desc(m.get("description"), m.get("agentType"))},
                      open(os.path.join(sub, jl), "w"))
        elif jl.endswith(".jsonl"):
            jsonl(p, os.path.join(sub, jl))
    json.dump({"phases": [
        {"name": "Build", "status": "running", "agents": ["backend-engineer", "mobile-engineer", "frontend-engineer"]},
        {"name": "Review", "status": "pending", "agents": ["code-reviewer", "security-reviewer"]},
        {"name": "Ship", "status": "pending", "agents": []}], "current": 0, "updated": "2026-10-14T07:00:00Z"},
        open(os.path.join(OUT, "phase.json"), "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
