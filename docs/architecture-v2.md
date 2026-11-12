# Agent Monitor v2: architecture (Wave-0 findings) (verified 2026-11-09, Claude Code 2.1.319)

Sources: `claude --help` (2.1.319), live runs from `/tmp/claude-1000/am-rec` (fixtures in this dir),
claude-agent-sdk 0.2.179 wheel source (downloaded, not installed or run: `/tmp/claude-1000/am-sdk/x/claude_agent_sdk/`),
https://code.claude.com/docs/en/agent-sdk/python. context7 MCP was unavailable this session, so the docs page was fetched directly.

Fixtures:
- `stream-recording.jsonl` / `stream-stdin.jsonl`: lead dispatches 1 general-purpose subagent, the subagent's Bash asks for permission, it is **allowed**, then hands back. 59 lines, session `00a9be51-d8e3-4c86-a657-3e6dfb152646`, $0.21.
- `stream-deny.jsonl` / `stream-deny-stdin.jsonl`: the lead's own Bash is **denied**.
- Account email in the `initialize` response was replaced with `REDACTED`. No tokens or keys appeared (`apiKeySource: "none"`, OAuth).
- Real past T2 CDT session for the M1 fixture test (do not copy it, read it in place):
  `~/.claude/projects/-home-victor-HT2026-mjukvaruprojektmetoder-g2-husqvarna-robot/cb492573-7564-46f0-ab1d-df4568c13342.jsonl`
  (1.3 MB, 5 `subagents/agent-*.meta.json` (backend, mobile, frontend, code-reviewer, security-reviewer), all `run_in_background: true`, "tier T2" x16; its cwd has `.claude/runtime/phase.json`).
  A bigger one: `~/.claude/projects/-home-victor/a2610f0c-2c83-4182-9246-11952b2c11aa.jsonl` (15 agents, 7.2 MB).

## 1. Driving Claude Code with the user's full harness

**Decision: use `claude -p` stream-json directly. Do not use the SDK.** The SDK runs the same CLI binary over the same pipe
(`_internal/transport/subprocess_cli.py:574` builds `[cli, "--output-format","stream-json","--verbose", ...]`, and `:793` always adds `--input-format stream-json`).
It also adds an asyncio dependency, and we get no extra capability from it.

Exact command (verified working):
```
claude -p --input-format stream-json --output-format stream-json --verbose \
       --permission-prompt-tool stdio --permission-mode <mode> [--resume <session_id>] [--model <m>]
cwd = the project directory. Do NOT pass --setting-sources, --bare, --safe-mode, --restricted, --dangerously-skip-permissions.
```
- Settings load when `--setting-sources` is omitted. Help: `--setting-sources <sources>  Comma-separated list of setting sources to load (user, project, local).`
  SDK docs: "`setting_sources` ... `None` (CLI defaults: all sources)" and "When omitted ... loads the same filesystem settings as the Claude Code CLI: user, project, and local."
  In the SDK source (`subprocess_cli.py:729`) the flag is only added when the option is set.
- **Observed** in `stream-recording.jsonl`: `system/init` lists `"plugins"` (20 entries, including `cdt@claude-dev-team` 1.66.2, ponytail, claude-mem, superpowers),
  `"agents"` (25 entries, including `cdt:architect`), `"slash_commands"` (156 entries, including `"cdt:orchestration"`), `"permissionMode":"default"`.
  Hooks ran: lines 1-14 are `system/hook_started|hook_response` for `SessionStart` (x7), then `UserPromptSubmit`, `PreToolUse`, `SubagentStart`, `SubagentStop`, `Stop`.
  These only appear with `--include-hook-events`, which I used for the recording. Line 49 shows a CDT hook firing: `"PreToolUse:Agent says: CDT dispatch: general-purpose · Touch x.txt"`.
- `--bare` help: "skip hooks ... plugin sync ... CLAUDE.md auto-discovery". That is why it must never be used.
- **`--permission-mode` must always be passed.** `~/.claude/settings.json` has `"defaultMode": "auto"`, so without the flag the auto classifier approves tools and no permission card ever reaches the UI.
  Help lists the choices `"acceptEdits","auto","bypassPermissions","manual","dontAsk","plan"`. `default` is not listed, but `--permission-mode default` is accepted, and init then reports `"permissionMode":"default"`.
- `--permission-prompt-tool` is not listed in help but is accepted (used by the SDK at `subprocess_cli.py:631`). `--permission-prompts <target>` (default `"host"`): "Who answers permission prompts with --print: "host" (the SDK host or --permission-prompt-tool) or "none"". Leave it at the default.
- Other flags (from help): `--include-partial-messages` (token-level chunks, print + stream-json only; its shape is NOT recorded, so skip it in v2),
  `--replay-user-messages` (echoes stdin user messages back; not needed), `--forward-subagent-text` ("Forward subagent text and thinking blocks ... with parent_tool_use_id set"; not needed, see the node log below),
  `--include-hook-events`, `--fork-session`, `--session-id <uuid>`, `--max-budget-usd`.
- Handshake: send `{"type":"control_request","request_id":"req_1_init","request":{"subtype":"initialize","hooks":null}}` first, as the SDK does (`query.py:350`).
  The reply is a `control_response` with `commands, agents, models, account, pid, current_permission_mode, ...`.
- User turn line, from the SDK (`client.py:248`):
  `{"type":"user","message":{"role":"user","content":"<text, slash commands verbatim>"},"parent_tool_use_id":null,"session_id":"default"}`

## 2. Subagent events → graph

Observed sequence (line numbers in `stream-recording.jsonl`):
| line | event | key fields |
|---|---|---|
| 22 | `system/init` | `session_id`, `model`, `cwd`, `permissionMode` |
| 23 | `assistant`, `parent_tool_use_id:null` | `tool_use` `{"id":"toolu_01Gm…","name":"Agent","input":{"description","subagent_type","prompt","run_in_background":false}}` → **dispatch** |
| 27 | `system/task_started` | `task_id:"aa0949f82fdc2a041"` (= agent_id), `tool_use_id:"toolu_01Gm…"`, `subagent_type`, `description`, `is_backgrounded`, `spawn_depth` |
| 29,33,40 | `user`/`assistant` with `parent_tool_use_id:"toolu_01Gm…"`, `agent_id` | the subagent's own messages and tool calls (they count toward that node's tools) |
| 31 | `system/task_progress` | `tool_use_id`, `description` ("Running …"), `usage:{total_tokens,tool_uses,duration_ms}`, `last_tool_name` |
| 36 | `control_request can_use_tool` | `agent_id:"aa0949f82fdc2a041"` → this is the subagent's node |
| 45 | `system/task_updated` | `patch:{status:"completed",end_time}` (no tool_use_id; map it with task_id) |
| 46 | `system/task_notification` | `tool_use_id`, `status:"completed"`, `summary`, `usage`, `output_file` → **handback** |
| 50 | `user`, `parent_tool_use_id:null` | `tool_result` for `toolu_01Gm…`, plus top-level `tool_use_result:{status,agentId,agentType,toolsUsed,content…}` |
| 59 | `result` | `subtype`, `total_cost_usd`, `session_id` |

Rules:
- Node id = the Agent/Task `tool_use.id`. A subagent message's `parent_tool_use_id` names the node it belongs to (null means the lead).
  Map `agent_id` → node with `task_started.task_id`.
- An Agent tool_use emitted by a subagent (`parent_tool_use_id = X`) gets `parent = X`, which handles nesting. Transcript meta also has `parentAgentId` and `spawnDepth: 2`.
- **Background agents** (`run_in_background:true`, which is what CDT uses in practice): the tool_result arrives immediately with the text
  `"Async agent launched successfully. …"`, and that is NOT a handback. The real handback is `system/task_notification` in the stream.
  In transcripts it is a `{"type":"queue-operation","operation":"enqueue","content":"<task-notification>\n<task-id>…</task-id>\n<tool-use-id>toolu_…</tool-use-id>\n<output-file>…</output-file>\n<status>completed</status>\n<summary>…</summary>…"}` line
  (verified in the husqvarna T2 transcript).
- Driven sessions are also written to disk: `~/.claude/projects/-tmp-claude-1000-am-rec/00a9be51….jsonl` plus `…/subagents/agent-aa0949f82fdc2a041.{jsonl,meta.json}` (`entrypoint:"sdk-cli"`; terminal sessions have `"cli"`).
  **Node log = read `subagents/agent-<agent_id>.jsonl`.** This works the same for driven and observed sessions, so `--forward-subagent-text` is not needed.

## 3. Permissions and interrupt (control protocol over stdin/stdout)

Request (CLI → host, verbatim from line 36):
```json
{"type":"control_request","request_id":"4eea2561-7864-418b-9d60-c200f96a2d28","request":{"subtype":"can_use_tool","tool_name":"Bash","display_name":"Bash","input":{"command":"touch x.txt","description":"Create empty file x.txt"},"description":"Create empty file x.txt","permission_suggestions":[{"type":"addRules","rules":[{"toolName":"Bash","ruleContent":"touch x.txt"}],"behavior":"allow","destination":"localSettings"},{"type":"addDirectories","directories":["/tmp/claude-1000/am-rec"],"destination":"session"},{"type":"setMode","mode":"acceptEdits","destination":"session"}],"blocked_path":"/tmp/claude-1000/am-rec/x.txt","tool_use_id":"toolu_01KcanRqUVogCmHTeDZE5eVX","agent_id":"aa0949f82fdc2a041"}}
```
`agent_id` is absent when the lead itself asks (see `stream-deny.jsonl`).

Allow (host → CLI, sent and accepted; x.txt was created):
```json
{"type":"control_response","response":{"subtype":"success","request_id":"4eea2561-7864-418b-9d60-c200f96a2d28","response":{"behavior":"allow","updatedInput":{"command":"touch x.txt","description":"Create empty file x.txt"}}}}
```
Deny (sent and accepted; y.txt was NOT created; the CLI emitted a tool_result `is_error:true`, `"content":"Denied in Agent Monitor"`, `permission_decision:{decision:"reject",source:"user_reject"}`):
```json
{"type":"control_response","response":{"subtype":"success","request_id":"4481bf95-5cae-4909-8d95-e7afcba4b122","response":{"behavior":"deny","message":"Denied in Agent Monitor"}}}
```
The SDK also supports `"interrupt": true` on deny and `"updatedPermissions": [...]` on allow (`query.py:645-663`). **v2 does not expose `updatedPermissions`**, so there is no "always allow" path that writes settings.
If an error is returned, `query.py:720+` sends a `control_response` with `subtype:"error"`. The CLI may send `control_cancel_request` (`query.py:449`), and the UI card should then close (not observed).

Interrupt (verified, resumed session, scratch run):
```
→ {"type":"control_request","request_id":"int1","request":{"subtype":"interrupt"}}
← {"type":"control_response","response":{"subtype":"success","request_id":"int1","response":{"still_queued":[]}}}
← {"type":"user","message":{"role":"user","content":[{"type":"text","text":"[Request interrupted by user]"}]},"parent_tool_use_id":null,...}
← {"type":"result","subtype":"error_during_execution",...}
```
The process stays alive after this, waiting on stdin. Set the mode at runtime with `{"subtype":"set_permission_mode","mode":"<m>"}` (`query.py:825`, not exercised).
Shutdown, mirroring the SDK (`subprocess_cli.py:1024-1046`): close stdin, wait 5 s, SIGTERM, wait 5 s, SIGKILL.

## 4. Continuing a session

- `system/init.session_id` (also on every event and on `result`) is the id to resume.
- Verified: `--resume 00a9be51-…` from the same cwd → init `session_id` was identical and the model had the prior context.
- Terminal sessions are stored in the same place (`~/.claude/projects/<cwd-slug>/<id>.jsonl`, `entrypoint:"cli"`). `--resume <id>` takes "session ID or name" (help).
  **Not verified on a real terminal session** (I did not want to modify one). Requirements: spawn with that session's `cwd`.
  If the transcript changed in the last 30 s (still live in a terminal), use `--fork-session` ("create a new session ID instead of reusing the original") so there are not two writers.

## 6. Design

### Modules (stdlib only)
| file | role |
|---|---|
| `graph.py` | pure reducer: events → graph JSON, plus a transcript→events adapter. No I/O except the adapter reading files |
| `driver.py` | `Session`: one `claude -p` child, reader/stderr threads, an event list, pending permissions |
| `server.py` | existing v1 observe code + auth + routes + SSE + `/vendor/` static |
| `index.html` | UI (cytoscape graph, chat, prompt, permission cards). `vendor/cytoscape.min.js` **already exists** (3.34.4, sha256 `081591ab…6cd8`, MIT license next to it; npm `cytoscape@3.34.4`, https://registry.npmjs.org/cytoscape/-/cytoscape-3.34.4.tgz) |

```python
# graph.py
def reduce(events: list[dict], phase: dict | None = None) -> dict: ...
def events_from_transcript(session_jsonl: str) -> list[dict]:
    """main jsonl + <sid>/subagents/agent-*.meta.json + queue-operation <task-notification> → stream-shaped events
       (assistant/user with parent_tool_use_id, system/task_started, system/task_notification)."""

# driver.py
MODES = ("default", "acceptEdits", "plan")          # never bypassPermissions/auto/dontAsk from the UI
CLAUDE = os.environ.get("AM_CLAUDE", "claude")       # tests point this at tests/fake_claude.py
class Session:
    def __init__(self, cwd: str, mode: str = "default", resume: str | None = None, fork: bool = False, model: str | None = None): ...
    id: str            # local uuid4 hex (exists before init arrives)
    sid: str | None    # claude session_id from system/init
    events: list[dict] # every stdout JSON line + synthetic {"type":"am_answered","request_id","behavior"} / {"type":"am_exit","code"}
    pending: dict[str, dict]   # request_id -> can_use_tool request
    def prompt(self, text: str) -> None
    def answer(self, request_id: str, allow: bool, message: str = "Denied in Agent Monitor") -> None   # allow → updatedInput = original input
    def interrupt(self) -> None
    def set_mode(self, mode: str) -> None              # ValueError if mode not in MODES
    def wait(self, since: int, timeout: float = 15) -> list[dict]   # Condition-based, for SSE
    def close(self) -> None                            # stdin close → 5s → SIGTERM → 5s → SIGKILL
```
Popen settings: `stdin/stdout/stderr=PIPE, text=True, bufsize=1, start_new_session=True`, a write lock around stdin, and drain stderr in a thread (otherwise the pipe fills up and deadlocks).
On child exit, append `am_exit` and clear `pending` (cards become stale).

### Graph JSON (output of `reduce`, also sent as SSE `graph` events)
```json
{"session":{"id":"<claude sid>","cwd":"…","model":"claude-sonnet-5-5","mode":"default","status":"running|idle|waiting|ended","cost_usd":0.21},
 "nodes":[
  {"id":"lead","kind":"lead","label":"lead","model":"…","status":"running","tools":0,"tokens":null,"parent":null},
  {"id":"toolu_01Gm…","kind":"agent","label":"general-purpose","agent_type":"general-purpose","agent_id":"aa0949f82fdc2a041",
   "description":"Touch x.txt","status":"running|waiting|done|error","tools":1,"tokens":31811,"current":"Running Create empty file x.txt",
   "parent":"lead","background":false,"wave":0,"started":"<iso>","ended":"<iso>|null"}],
 "edges":[
  {"id":"d:toolu_01Gm…","source":"lead","target":"toolu_01Gm…","kind":"dispatch","label":"Touch x.txt"},
  {"id":"h:toolu_01Gm…","source":"toolu_01Gm…","target":"lead","kind":"handback","label":"DONE …(summary, 120 chars)"}],
 "waves":[{"index":0,"name":"Build","status":"running","agents":["general-purpose"]}],
 "permissions":[{"request_id":"4eea…","node":"toolu_01Gm…","tool_name":"Bash","description":"Create empty file x.txt","input":{},"blocked_path":"…"}]}
```
Reducer rules: init → session; assistant tool_use Agent|Task → node + dispatch edge (`parent` = msg.parent_tool_use_id or "lead");
assistant/user with `parent_tool_use_id` X → node X (`tools++` per tool_use); `task_started` → agent_id, background, running;
`task_progress` → tokens/tools/current; `can_use_tool` → card + node `waiting` (node via agent_id, else lead); `am_answered`/`control_cancel_request` → card removed;
`task_notification` → `done` (`completed`) / `error` (other) + handback edge; a non-background tool_result for the node id is the fallback handback,
and tool_results starting with "Async agent launched" are ignored; `result` → session `idle`; `am_exit` → `ended`.
Wave = when dispatched, the index of the first phase with `status=="running"` whose `agents` contains `agent_type.split(":")[-1]`; if none, the first phase that lists it; otherwise null.
phase.json is a snapshot of the current state (`{"phases":[{name,status,agents}],"current":i,"updated":ts}`), so the driver re-reads it on each dispatch.

### HTTP API (127.0.0.1 only)
```
GET  /                         index.html (no token; it contains no data)
GET  /vendor/cytoscape.min.js  static, no token
GET  /api/state                v1 observed sessions (+ "graph" per session via events_from_transcript)   [token]
GET  /api/sessions             [{id,sid,cwd,mode,status}]                                              [token]
POST /api/sessions             {"cwd","prompt","mode"?, "resume"?, "fork"?} → {"id"}                   [token+origin]
POST /api/sessions/<id>/prompt      {"text"}                                                           [token+origin]
POST /api/sessions/<id>/permission  {"request_id","behavior":"allow"|"deny"}  → 404 if not pending     [token+origin]
POST /api/sessions/<id>/interrupt   {}                                                                 [token+origin]
POST /api/sessions/<id>/mode        {"mode"}  → 400 unless in MODES                                    [token+origin]
GET  /api/sessions/<id>/events?t=<token>   SSE: "id: <n>\nevent: ev\ndata: <raw event json>\n\n" and "event: graph\ndata: <graph>\n\n"; honors Last-Event-ID; ": ping" every 15 s
GET  /api/log?session=<sid>&node=<agent_id|lead>   node transcript lines (from ~/.claude/projects)        [token]
```
Security: the token comes from `secrets.token_urlsafe(32)` on every start and is written with `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` to `~/.config/agent-monitor/token`.
The launcher opens `http://127.0.0.1:7777/#t=<token>`. JS reads it from `location.hash` and sends `X-AM-Token` (EventSource cannot set headers, so SSE uses `?t=`).
Compare with `hmac.compare_digest`. Reject requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding).
POST requires `Origin` equal to `http://127.0.0.1:<port>` / `http://localhost:<port>` and `Content-Type: application/json` (CSRF), and bodies are capped at 1 MB.
The `cwd` in POST must be an existing directory. No endpoint accepts arbitrary CLI flags.

### Builder file ownership
- **A, graph (M1):** `graph.py`, `test_graph.py`, `tests/fixtures/**` (copy `docs/research/stream-*.jsonl` there). Reads: this file, server.py, the husqvarna transcript.
- **B, backend (M2/M3):** `server.py`, `driver.py`, `test_server.py`, `test_driver.py`, `tests/fake_claude.py` (replays a fixture, answers initialize/interrupt, and blocks on can_use_tool until it receives a control_response). Reads: graph.py interface.
- **C, frontend:** `index.html` (`vendor/**` read-only). Reads: graph JSON + API above, `design/**`.
- **D, Linux app (M4):** `packaging/**` (.desktop, systemd --user unit, launcher, icon).

## Unverified / risks
- `/cdt:orchestration …` sent as user content: `cdt:orchestration` is listed in init `slash_commands`, but I did not run the expansion (cost).
- Resume of a `cli`-origin (terminal) session; resuming a session that is live in another process.
- `control_cancel_request` shape, `set_permission_mode`, and `--include-partial-messages` event shapes are not recorded.
- A child that never receives `initialize` was not tested. Always send it.
- Every run costs at least $0.11 because of the system prompt with 20 plugins (a 1-word prompt cost $0.115). Integration tests must use the fake claude.
- The `auto` mode is excluded from the UI on purpose (the classifier auto-approves). Flag this to the user, since it is their default.

## 7. Decisions taken by the lead (override §6 where they differ)

1. **No long-lived token in URLs.** `chromium --app=<url>` puts the URL in `/proc/<pid>/cmdline`, which every local process can read.
   - The server creates `token = secrets.token_urlsafe(32)` on every start and writes it to `~/.config/agent-monitor/token` with 0600. The directory gets 0700.
   - The launcher reads the token and calls `POST /api/once` with header `X-AM-Token: <token>` and no Origin. The server answers `{"once":"<nonce>"}`. The nonce is single use and expires after 30 s.
   - The launcher opens `http://127.0.0.1:<port>/login?once=<nonce>`. The server burns the nonce and answers `303 → /` with `Set-Cookie: am=<token>; HttpOnly; SameSite=Strict; Path=/`.
   - The API accepts the `am` cookie or the `X-AM-Token` header, and compares them with `hmac.compare_digest`. SSE uses the cookie, so the token never appears in a query string.
   - `/`, `/login` and `/vendor/*` need no token, and `/` contains no data.
2. **Host check on every request:** `Host` must be exactly `127.0.0.1:<port>` or `localhost:<port>`. Otherwise the server answers 403.
   **Origin check on every POST:** a browser always sends Origin, so if Origin is present it must equal `http://127.0.0.1:<port>` or `http://localhost:<port>`, otherwise 403. A POST without Origin (curl or the launcher) still needs the token header. POSTs must have `Content-Type: application/json` and a body of at most 1 MB. There are no CORS headers at all.
   SSE GETs and `/api/log` also check Origin when it is present.
3. **Permission modes in the UI:** `default`, `acceptEdits` and `plan` only. `auto`, `dontAsk` and `bypassPermissions` cannot be chosen, and the server rejects them. `auto` is the user's terminal default, but its classifier approves tools on its own, so permission cards would never appear. `--permission-mode` is always passed.
4. **Transcript fixtures in git are scrubbed.** `tests/fixtures/` holds only structural fields. Prompt and response text is replaced, so a future push of the repo cannot leak private transcripts.
5. **Logging:** the server never logs request headers, tokens, cookies or event bodies. `log_message` is a no-op, and errors print only the exception type and route.
