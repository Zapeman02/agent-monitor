"""Pure reducer: Claude Code stream-json events -> Agent Monitor graph JSON (docs/architecture-v2.md sec. 6).

Also adapts on-disk transcripts (main jsonl + subagents/) into stream-shaped events. Stdlib only.
"""
import glob, json, os, re, time

TAIL = 400_000   # bytes read from the end of each transcript
AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
NOTE_TAG = re.compile(r"<(task-id|tool-use-id|status|summary)>(.*?)</\1>", re.S)
TEXT_MAX = 4000
RUNNING_S = 120   # a finished-looking subagent file quiet for this long counts as done


def tail_lines(path, n=TAIL):
    with open(path, "rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - n))
        data = f.read().decode("utf-8", "replace").splitlines()
    out = []
    for l in data[1 if size > n else 0:]:   # first line may be cut in half
        try: out.append(json.loads(l))
        except Exception: pass
    return out


def tool_label(name, inp):
    inp = inp or {}
    if name == "Bash": return inp.get("description") or inp.get("command", "")[:80]
    if name in ("Read", "Write", "Edit"): return os.path.basename(inp.get("file_path", ""))
    if name in ("Agent", "Task"): return f'{inp.get("subagent_type", "agent")}: {inp.get("description", "")}'
    if name == "Skill": return inp.get("skill", "")
    if name in ("Grep", "Glob"): return inp.get("pattern", "")
    return next((str(v)[:60] for v in inp.values() if isinstance(v, str)), "")


def _truthy(v):
    return v is True or (isinstance(v, str) and v.lower() == "true")


def _result_text(c):
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return c if isinstance(c, str) else ""


def _phases(phase):
    ps = phase.get("phases") if isinstance(phase, dict) else None
    return [p for p in ps if isinstance(p, dict)] if isinstance(ps, list) else []


def _wave_of(phase, agent_type):
    phases = _phases(phase)
    t = (agent_type or "").split(":")[-1]
    for want_running in (True, False):
        for i, p in enumerate(phases):
            if t in (p.get("agents") if isinstance(p.get("agents"), list) else []) and (not want_running or p.get("status") == "running"):
                return i
    return None


# cdt-phase only counts as the command word of a shell command (not an argument, pipe target or comment)
_CDT_PHASE = re.compile(r"""(?:^|[;&|\n])\s*(?:[~\w.-]*/)*cdt-phase\s+(?:"([^"]*)"|'([^']*)'|([^\s"'-][^\s"']*))""")


def _phase_name(cmd):
    m = _CDT_PHASE.search(cmd.split("<<")[0]) if isinstance(cmd, str) else None   # heredoc bodies don't count
    if not m:
        return None
    raw = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
    name = " ".join(raw.split())
    return None if not name or (m.group(3) is not None and name == "done") else name


def reduce(events, phase=None):
    sess = {"id": None, "cwd": None, "model": None, "mode": None, "status": "running", "cost_usd": None}
    lead = {"id": "lead", "kind": "lead", "label": "lead", "model": None, "status": "running",
            "tools": 0, "tokens": None, "parent": None}
    nodes, edges = {"lead": lead}, {}
    by_agent = {}     # agent_id -> node id
    perms = {}        # request_id -> card (+ private "_tool_use_id")
    seen = set()      # tool_use ids / message ids already counted
    base = {}         # node id -> status before the "waiting" overlay
    cur = [None]      # latest cdt-phase name from the lead's Bash calls
    extra = []        # cdt-phase names unknown to phase.json, in order of first appearance
    names = [" ".join(str(p.get("name")).split()) for p in _phases(phase)]

    def wave_for(atype):
        if cur[0] is None:
            return _wave_of(phase, atype)
        return (names + extra).index(cur[0])

    totals = {}       # am_lead_totals: whole-file lead tokens/tools, override the windowed sums
    reported = {}     # node id -> (tokens, tools) from task_progress / task_notification

    def touch(n, ev):
        if n and ev.get("timestamp") and not n.get("started"):
            n["started"] = ev["timestamp"]

    def ensure(nid, ev, **kw):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "kind": "agent", "label": "agent", "model": None, "status": "running",
                          "tools": 0, "tokens": 0, "parent": "lead", "agent_type": None, "agent_id": None,
                          "description": "", "current": None, "background": False, "wave": None,
                          "started": None, "ended": None, **kw}
            base[nid] = "running"
        touch(nodes[nid], ev)
        return nodes[nid]

    def handback(nid, ev, status, text):
        n = nodes[nid]
        base[nid] = status
        n["ended"] = ev.get("timestamp")
        n["current"] = None
        edges["h:" + nid] = {"id": "h:" + nid, "source": nid, "target": n["parent"], "kind": "handback",
                             "label": (text or "").strip()[:120]}

    def message(ev):
        m = ev.get("message") or {}
        owner = ev.get("parent_tool_use_id")
        n = ensure(owner, ev) if owner else lead
        if owner:
            if ev.get("agent_id"):
                n["agent_id"] = ev["agent_id"]
                by_agent[ev["agent_id"]] = owner
        u = m.get("usage")
        if ev["type"] == "assistant" and u and m.get("id") not in seen:
            seen.add(m.get("id"))
            n["tokens"] = (n["tokens"] or 0) + sum(
                u.get(k) or 0 for k in ("input_tokens", "output_tokens",
                                        "cache_creation_input_tokens", "cache_read_input_tokens"))
        if ev["type"] == "assistant":
            n["model"] = m.get("model") or n["model"]
            sess["status"] = "waiting" if perms else "running"
        c = m.get("content")
        for x in c if isinstance(c, list) else []:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_use" and x.get("id") not in seen:
                seen.add(x.get("id"))
                n["tools"] += 1
                inp = x.get("input") or {}
                if not owner and x.get("name") == "Bash":
                    pn = _phase_name(inp.get("command"))
                    if pn:
                        cur[0] = pn
                        if pn not in names + extra:
                            extra.append(pn)
                if owner:
                    n["current"] = "Running " + tool_label(x.get("name"), inp)
                if x.get("name") in ("Agent", "Task"):
                    nid, atype = x["id"], inp.get("subagent_type") or "agent"
                    ensure(nid, ev, kind="agent", label=atype.split(":")[-1], agent_type=atype,
                           description=inp.get("description", ""), background=_truthy(inp.get("run_in_background")),
                           parent=owner if owner in nodes else "lead", wave=wave_for(atype))
                    p = nodes[nid]["parent"]
                    edges["d:" + nid] = {"id": "d:" + nid, "source": p, "target": nid, "kind": "dispatch",
                                         "label": inp.get("description", "")}
            elif x.get("type") == "tool_result":
                tid = x.get("tool_use_id")
                for rid in [r for r, c in perms.items() if c["_tool_use_id"] == tid]:
                    del perms[rid]
                text = _result_text(x.get("content"))
                if tid in nodes and nodes[tid]["kind"] == "agent" and base[tid] == "running" \
                        and not text.startswith("Async agent launched"):
                    handback(tid, ev, "error" if x.get("is_error") else "done", text)

    def system(ev):
        st, nid = ev.get("subtype"), ev.get("tool_use_id")
        if st == "am_lead_totals":
            totals.update(tokens=ev.get("tokens"), tools=ev.get("tools"))
        elif st == "init":
            sess.update(id=ev.get("session_id"), cwd=ev.get("cwd"), model=ev.get("model"), mode=ev.get("permissionMode"))
            lead["model"] = ev.get("model") or lead["model"]
        elif st == "task_started":
            atype = ev.get("subagent_type") or "agent"
            n = ensure(nid, ev, kind="agent", label=atype.split(":")[-1], agent_type=atype,
                       description=ev.get("description", ""), wave=wave_for(atype))
            n["agent_id"] = ev.get("task_id")
            n["background"] = n["background"] or bool(ev.get("is_backgrounded"))
            by_agent[ev.get("task_id")] = nid
            if "d:" + nid not in edges:   # task_started without a seen Agent tool_use (e.g. tail-truncated)
                edges["d:" + nid] = {"id": "d:" + nid, "source": "lead", "target": nid, "kind": "dispatch",
                                     "label": ev.get("description", "")}
        elif st in ("task_progress", "task_notification"):
            n = nodes.get(nid or by_agent.get(ev.get("task_id")))   # unknown node: ignore, never create an orphan
            if n is None or n["id"] == "lead":
                return
            u = ev.get("usage") or {}
            reported[n["id"]] = (u.get("total_tokens"), u.get("tool_uses"))
            if st == "task_progress":
                n["current"] = ev.get("description") or n["current"]
            elif base[n["id"]] == "running" or "h:" + n["id"] not in edges:
                handback(n["id"], ev, "done" if ev.get("status") == "completed" else "error", ev.get("summary"))

    for ev in events:
        try:
            t = ev.get("type")
            if ev.get("session_id") and not sess["id"]:
                sess["id"] = ev["session_id"]
            if t in ("assistant", "user"):
                message(ev)
            elif t == "system":
                system(ev)
            elif t == "control_request" and (ev.get("request") or {}).get("subtype") == "can_use_tool":
                r = ev["request"]
                perms[ev["request_id"]] = {
                    "request_id": ev["request_id"], "node": by_agent.get(r.get("agent_id"), "lead"),
                    "tool_name": r.get("tool_name"), "description": r.get("description") or "",
                    "input": r.get("input") or {}, "blocked_path": r.get("blocked_path"),
                    "_tool_use_id": r.get("tool_use_id")}
                sess["status"] = "waiting"
            elif t in ("am_answered", "control_cancel_request"):
                perms.pop(ev.get("request_id"), None)
                sess["status"] = "waiting" if perms else "running"
            elif t == "result":
                sess["status"] = "idle"
                sess["cost_usd"] = ev.get("total_cost_usd", sess["cost_usd"])
            elif t == "am_exit":
                sess["status"] = "ended"
                perms.clear()
        except Exception:   # a malformed event must never break the monitor
            continue

    if totals:
        lead["tokens"], lead["tools"] = totals["tokens"], totals["tools"]
    waiting = {c["node"] for c in perms.values()}
    for nid, n in nodes.items():
        if nid == "lead":
            n["status"] = "waiting" if "lead" in waiting else ("done" if sess["status"] in ("idle", "ended") else "running")
            continue
        n["status"] = "waiting" if nid in waiting and base[nid] == "running" else base[nid]
        tok, tools = reported.get(nid, (None, None))
        n["tokens"] = tok if tok is not None else n["tokens"]
        n["tools"] = max(n["tools"], tools or 0)
    phases = _phases(phase)
    waves = [{"index": i, "name": p.get("name"), "status": p.get("status"), "agents": p.get("agents") or []}
             for i, p in enumerate(phases)]
    waves += [{"index": len(phases) + k, "name": nm, "status": "running" if nm == cur[0] else "done", "agents": []}
              for k, nm in enumerate(extra)]
    return {"session": sess, "nodes": list(nodes.values()), "edges": list(edges.values()), "waves": waves,
            "permissions": [{k: v for k, v in c.items() if k != "_tool_use_id"} for c in perms.values()]}


def events_from_transcript(session_jsonl, max_bytes=4_000_000):
    """Stream-shaped events from a transcript. Subagent tokens: reduce() sums input+output+cache_creation+cache_read
    over distinct assistant message ids of the subagent jsonl (cache reads recur per turn, so this is processed tokens)."""
    sid = os.path.splitext(os.path.basename(session_jsonl))[0]
    main = tail_lines(session_jsonl, max_bytes)
    evs = []
    first = next((d for d in main if d.get("cwd")), {})
    model = next(((d.get("message") or {}).get("model") for d in main if d.get("type") == "assistant"), None)
    evs.append({"type": "system", "subtype": "init", "session_id": sid, "cwd": first.get("cwd"), "model": model,
                "permissionMode": next((d.get("permissionMode") for d in reversed(main) if d.get("type") == "permission-mode"), None),
                "timestamp": ""})
    for d in main:
        if d.get("type") in ("assistant", "user") and not d.get("isSidechain"):
            evs.append({**d, "parent_tool_use_id": None, "session_id": sid})
    notified, seen = set(), {d.get("uuid") for d in main}
    early, tok_ids, tool_ids, tokens = [], set(), set(), 0
    with open(session_jsonl, "rb") as fh:   # early handbacks, dispatches and cdt-phase calls may sit outside the tail window
        for raw in fh:
            note = b'"queue-operation"' in raw and b"task-notification" in raw
            lead_call = b'"assistant"' in raw and (b"cdt-phase" in raw or b'"name":"Agent"' in raw or b'"name":"Task"' in raw)
            if not (note or lead_call or b'"assistant"' in raw):
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if d.get("type") == "assistant" and not d.get("isSidechain"):   # lead totals over the whole file
                m = d.get("message") or {}
                u = m.get("usage")
                if u and m.get("id") not in tok_ids:
                    tok_ids.add(m.get("id"))
                    tokens += sum(u.get(k) or 0 for k in ("input_tokens", "output_tokens",
                                                          "cache_creation_input_tokens", "cache_read_input_tokens"))
                c = m.get("content")
                if isinstance(c, list):
                    tool_ids.update(x.get("id") for x in c if isinstance(x, dict) and x.get("type") == "tool_use")
            if not (note or lead_call):
                continue
            if lead_call and not note:
                if d.get("type") == "assistant" and not d.get("isSidechain") and d.get("uuid") not in seen:
                    seen.add(d.get("uuid"))
                    early.append({**d, "parent_tool_use_id": None, "session_id": sid})
                continue
            f = dict(NOTE_TAG.findall(str(d.get("content"))))
            if d.get("type") == "queue-operation" and f.get("task-id"):
                notified.add(f["task-id"])
                evs.append({"type": "system", "subtype": "task_notification", "task_id": f["task-id"],
                            "tool_use_id": f.get("tool-use-id"), "status": f.get("status"),
                            "summary": f.get("summary"), "timestamp": d.get("timestamp")})
    evs += early
    sub_dir = os.path.join(os.path.dirname(session_jsonl), sid, "subagents")
    for meta in sorted(glob.glob(os.path.join(sub_dir, "agent-*.meta.json"))):
        try:
            info = json.load(open(meta))
            aid = os.path.basename(meta)[6:-len(".meta.json")]
            sub = meta[:-len(".meta.json")] + ".jsonl"
            lines = tail_lines(sub, max_bytes)
            tu = info["toolUseId"]
            idle = time.time() - os.path.getmtime(sub) > RUNNING_S
        except Exception:
            continue
        first_ts = next((d.get("timestamp") for d in lines if d.get("timestamp")), "")
        evs.append({"type": "system", "subtype": "task_started", "task_id": aid, "tool_use_id": tu,
                    "subagent_type": info.get("agentType"), "description": info.get("description", ""),
                    "is_backgrounded": info.get("requestShape") == "background", "timestamp": first_ts})
        evs += [{**d, "parent_tool_use_id": tu, "agent_id": aid} for d in lines if d.get("type") in ("assistant", "user")]
        last = next((d for d in reversed(lines) if d.get("type") in ("assistant", "user")), {})
        if aid not in notified and idle and last.get("type") == "assistant" \
                and (last.get("message") or {}).get("stop_reason") == "end_turn":   # no notification, but finished and quiet
            evs.append({"type": "system", "subtype": "task_notification", "task_id": aid, "tool_use_id": tu,
                        "status": "completed", "summary": "", "timestamp": last.get("timestamp")})
    evs.sort(key=lambda e: e.get("timestamp") or "")   # stable: keeps file order within equal timestamps
    evs.append({"type": "system", "subtype": "am_lead_totals", "tokens": tokens, "tools": len(tool_ids)})
    return evs


def node_log(session_jsonl, node, limit=2000):
    if node == "lead":
        path = session_jsonl
    else:
        if not isinstance(node, str) or not AGENT_ID.fullmatch(node):
            raise ValueError("bad agent id")
        sid = os.path.splitext(os.path.basename(session_jsonl))[0]
        path = os.path.join(os.path.dirname(session_jsonl), sid, "subagents", f"agent-{node}.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    for d in tail_lines(path, 4_000_000):
        if d.get("type") not in ("assistant", "user"):
            continue
        c = (d.get("message") or {}).get("content")
        for x in [{"type": "text", "text": c}] if isinstance(c, str) else c or []:
            if not isinstance(x, dict):
                continue
            e = {"ts": d.get("timestamp"), "role": d["type"]}
            if x.get("type") == "text":
                e["text"] = x.get("text") or ""
            elif x.get("type") == "tool_use":
                e.update(role="tool_use", tool=x.get("name"), text=json.dumps(x.get("input"), ensure_ascii=False))
            elif x.get("type") == "tool_result":
                e.update(role="tool_result", text=_result_text(x.get("content")))
            else:
                continue
            e["text"] = e["text"][:TEXT_MAX]
            out.append(e)
    return out[-limit:]
