# Agent Monitor v2 — UI spec (Wave 0)

Scope: one Chromium `--app` window, typical 1400x900, must work down to 1000px wide. Visual language = v1
(`index.html`): dark, JetBrains Mono 13px/1.45, dot-grid background, 7-8px radii, 1px `--line` borders,
pills with `currentColor` border. UI copy is Swedish. No CDN: Cytoscape is vendored locally.

## 1. Tokens

Keep every v1 token on `:root` unchanged (`index.html:10-14`). Add only these:

```css
:root{
  --muted:#8593a0;   /* secondary TEXT on panels; v1 --dim is 4.4:1 on --panel (fails) */
  --pink:#e98fc0; --pink-bg:#2a1220;   /* waiting-for-permission (needs YOU) */
  --red-bg:#2a1414;                    /* error state fill */
  --focus:var(--blue);
  --r:7px; --gap:12px; --hit:32px;     /* radius, base gap, min control size */
}
```

Rules: `--dim` only on `--bg` (4.5:1) or for non-text (icons, borders). `--faint` (2.0:1) is NEVER text —
borders/grid only. All other secondary text uses `--muted`.

Node state palette (text = state color on its own fill; contrast measured, WCAG 2.x):

| State (data.status) | Swedish label | Border / text | Fill | Text on fill | Extra non-color cue |
|---|---|---|---|---|---|
| `running` | kör | `--amber` | `--amber-bg` | 8.0:1 | pulse (or static 3px border), `▶` prefix |
| `running` + review type (v1 `isReview`) | kör | `--violet` | `--violet-bg` | 7.2:1 | same as running |
| `waiting` (permission) | väntar på behörighet | `--pink` | `--pink-bg` | 7.6:1 | double border, `⏸` prefix |
| `done` | klar | `--green` | `--green-bg` | 9.5:1 | `✓` prefix |
| `error` | fel | `--red` | `--red-bg` | 6.1:1 | dashed border, `✕` prefix |
| `idle` / queued | väntar | `--line2` border, text `--muted` | `--panel` | 6.1:1 | none |
| selected (any) | — | `--blue` 3px overlay ring | unchanged | — | — |

Primary node text is `--text` (11.2–12.8:1 on every fill). Dark-on-color buttons use `--bg` text
(on `--blue` 10.4:1, `--green` 11.3:1, `--red` 7.1:1).

## 2. Layout grid

```css
.app{height:100vh;overflow:hidden;display:grid;
  grid-template-columns:260px minmax(0,1fr);
  grid-template-rows:40px minmax(0,1fr);
  grid-template-areas:"hdr hdr" "side main"}
header{grid-area:hdr}  aside{grid-area:side;overflow:auto;border-right:1px solid var(--line)}
main{grid-area:main;min-width:0;display:grid;grid-template-columns:minmax(0,1fr);
  grid-template-rows:44px minmax(220px,1fr) minmax(160px,34vh) auto auto;
  grid-template-areas:"bar" "graph" "chat" "perms" "prompt"}
.toolbar{grid-area:bar} #graph{grid-area:graph;position:relative} #chat{grid-area:chat;overflow:auto}
#perms{grid-area:perms;max-height:40vh;overflow:auto} #prompt{grid-area:prompt}
/* log panel overlaps graph+chat rows on the right, prompt stays usable */
#log{grid-row:2/4;grid-column:1;justify-self:end;width:min(440px,48%);z-index:5;
  background:var(--panel);border-left:1px solid var(--line2);overflow:auto;
  transform:translateX(100%);visibility:hidden;transition:transform .18s ease-out,visibility 0s .18s}
#log.open{transform:none;visibility:visible;transition:transform .18s ease-out}
@media (max-width:1150px){
  .app{grid-template-columns:220px minmax(0,1fr)}
  main{grid-template-rows:44px minmax(200px,1fr) minmax(140px,32vh) auto auto}
  #log{width:min(380px,62%)} }
```

- Header (40px): `// agent monitor · claude-dev-team`, live indicator (v1 `.live`), spacer, clock.
- Sidebar: `+ Ny session` button (full width, top), then two groups with v1 `.lbl` headings
  `Styrda` and `Observerade`. Items reuse v1 `.sess`; meta row adds a pill `styrd` (blue) / `observerad`
  (`--muted`) and, if any node waits, a pink pill `⏸ behörighet`.
- Toolbar (44px, flex, gap 10px): session title (600) + cwd (`--muted`, ellipsis) | spacer |
  view toggle `Graf | Lista` | permission-mode `<select>` | `Stoppa`.
- Perms row: stacked permission cards (only when pending). Prompt row: textarea + `Skicka`.
- Minimum control size `--hit` (32px) height, 32px min width; focus ring `outline:2px solid var(--focus);
  outline-offset:2px` on `:focus-visible` for every interactive element (incl. `.sess`, `summary`).

## 3. Components

**Ny session form** (inline under the button, not a modal): `<label>Arbetskatalog <input name=cwd>`
(prefilled with last-used cwd, required, `spellcheck=false`), `<label>Läge <select>` (same 3 modes),
`Starta` (primary, blue fill) + `Avbryt`. Enter submits. Server error shown inline under the input
(`--red`, `role=alert`), input gets `aria-invalid=true`.

**Permission-mode select** (driven sessions only): options exactly
`default` "Standard — fråga vid behov", `acceptEdits` "Godkänn redigeringar", `plan` "Planläge".
`bypassPermissions` must not exist in the DOM, the JS, or any option list. Label: `aria-label="Behörighetsläge"`.
Observed sessions: select is hidden.

**Stoppa**: red outline button (`--red` text/border on `--panel`, 6.8:1), enabled only while the session
is running (`disabled` + `aria-disabled` otherwise). One click stops; no confirm.

**Chat stream** (`#chat`): messages top-to-bottom, autoscroll only when user is within 40px of bottom;
otherwise show a floating `↓ Nya meddelanden` button. User prompt: `>` prefix, `--blue`. Assistant text:
`--text`, `white-space:pre-wrap`, streaming caret `▍` (blinks; static under reduced motion). Tool calls:
`<details class=tool><summary>⚙ {tool} · {inputSummary ≤80ch}</summary><pre>{input}\n—\n{result}</pre></details>`,
collapsed by default, summary in `--blue`, failed result → summary `--red` with `✕`.
Session ended: banner `Sessionen avslutades (kod N)` (`--muted`, or `--red` if N≠0).

**Permission card** (`#perms > .perm`): border 1px `--pink`, fill `--pink-bg`, radius `--r`, padding 10/12.
Content: heading `Behörighet krävs · {tool}` (pink, 600), agent name (`--muted`), input summary in `<pre>`
(max 6 lines, `Visa allt` toggle for the rest; for Bash show the command, for Edit/Write show the file path,
for others the first 300 chars of JSON). Buttons: `Tillåt` (green fill, `--bg` text) and `Neka` (outline,
`--red`), equal size, no autofocus. There is NO "tillåt alltid", "tillåt alla", or bypass option.
After click: card collapses to one line `✓ Tillåtet: Bash` / `✕ Nekat: Bash` in chat, buttons removed
(disable while the request is in flight to prevent double submit).

**Prompt** (`#prompt`): `<label class=sr-only for=q>Prompt</label><textarea id=q rows=1>` auto-grows to
max 160px; placeholder `Skriv en prompt eller /kommando … (Enter skickar, Shift+Enter ny rad)`.
- Enter (without Shift, and not `e.isComposing`) = send; Shift+Enter = newline.
- ArrowUp: history back only when the caret is on the first line; ArrowDown: forward only when on the
  last line. Current draft is kept and restored past the newest entry. History per session, last 100, localStorage.
- Text starting with `/` is sent verbatim (no parsing, no autocomplete). Empty/whitespace is not sent.
- Disabled (with visible reason as placeholder) when disconnected or for observed sessions.
- Observed session: prompt row replaced by bar `Observerad terminalsession — skrivskyddad` + primary
  button `Fortsätt här` (resumes; on success the session moves to `Styrda` and stays selected).

**Log panel** (`#log`, `role=complementary`, `aria-labelledby=log-h`): header with `<h2 id=log-h tabindex=-1>`
`{agent} · {model}` + status pill + close `✕` (`aria-label="Stäng logg"`). Meta row: tool calls, tokens,
start/slut time. Body: dispatch description, then the full log in the chat-stream format above,
then handback text. Opening moves focus to `#log-h`; Esc or ✕ closes and returns focus to the invoking
node-list button (or the graph container).

## 4. Cytoscape style spec

Resolve tokens at init: `const v = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()`.
Font: `'"JetBrains Mono", ui-monospace, monospace'`. Layout: `preset` (no physics) —
lead at x=0; wave *i* (0-based, from `phase.json` order) column x = 300·(i+1); nodes in a column at
y = 100·k, centred on 0. Agents without a known wave go into a trailing column `Övrigt`. No `phase.json` →
no compound groups, agents in one column by dispatch order. `cy.fit(undefined, 40)` on first render and
on new nodes only if the user has not panned/zoomed (track via `cy.on('viewport')` after user input).
`minZoom:.3, maxZoom:2, boxSelectionEnabled:false, autoungrabify:true`.

Node label: `data(label)` built in JS, 3 lines:
`{prefix} {short(type)}\n{modelName(model).toLowerCase()} · {statusSv}\n{toolCalls} verktyg · {fmtTok(tokens)}`
where `fmtTok` = `<1000 → "850 tok"`, else `"12.3k tok"`. Lead's first line is `lead`.

| Selector | Style |
|---|---|
| `node` | `shape:round-rectangle, width:200, height:66, background-color:v('--panel'), border-width:1.5, border-color:v('--line2'), label:data(label), color:v('--text'), font-family, font-size:11, text-wrap:wrap, text-max-width:184, text-valign:center, text-halign:center, line-height:1.35` |
| `node[?lead]` | `width:230, height:74, border-width:2, border-color:v('--green'), background-color:v('--green-bg'), font-weight:600` |
| `node[status="running"]` | `border-color:v('--amber'), background-color:v('--amber-bg'), border-width:2` |
| `node[status="running"][?review]` | `border-color:v('--violet'), background-color:v('--violet-bg')` |
| `node[status="waiting"]` | `border-color:v('--pink'), background-color:v('--pink-bg'), border-style:double, border-width:4` |
| `node[status="done"]` | `border-color:v('--green'), background-color:v('--green-bg')` |
| `node[status="error"]` | `border-color:v('--red'), background-color:v('--red-bg'), border-style:dashed` |
| `node.pulse` | `border-width:4, border-opacity:.45` + on base running: `transition-property:border-width border-opacity, transition-duration:.8s` |
| `node:selected` | `overlay-color:v('--blue'), overlay-opacity:.12, overlay-padding:5, border-color:v('--blue')` |
| `$node > node` (wave group, `data.wave`) | `shape:round-rectangle, background-color:v('--panel'), background-opacity:.35, border-width:1, border-style:dashed, border-color:v('--line2'), padding:18, label:data(label), text-valign:top, text-halign:center, text-margin-y:-6, font-size:10, color:v('--muted'), text-transform:uppercase, events:no` |
| `node.wave-current` | `border-style:solid, border-color:v('--blue'), color:v('--blue')` |
| `edge` | `width:1.5, curve-style:bezier, control-point-step-size:36, target-arrow-shape:triangle, arrow-scale:.9, line-color:v('--line2'), target-arrow-color:v('--line2')` |
| `edge[kind="dispatch"]` | `label:data(short), font-size:9, color:v('--muted'), text-background-color:v('--bg'), text-background-opacity:1, text-background-padding:2, text-rotation:autorotate` (`short` = description ≤28 chars + `…`) |
| `edge[kind="dispatch"].live` (target running/waiting) | `line-color:v('--amber'), target-arrow-color:v('--amber')` |
| `edge[kind="handback"]` | `line-style:dashed, line-dash-pattern:[6,4], line-color:v('--green'), target-arrow-color:v('--green'), target-arrow-shape:vee, label:''` |

Wave group label: `Wave {n} · {phase name}`; `wave-current` = the wave `phase.json` marks running.
Lead has no parent. Click/tap on a non-wave node → `cy.$(':selected').unselect(); node.select()` → open log.
Tap on background → unselect (panel stays open until closed explicitly).

Pulse: one `setInterval(…, 800)` toggling class `pulse` on `node[status="running"]`; stop it when no node
is running. Waiting nodes do not pulse (the double border + pink is the cue; avoid two competing motions).

## 5. Keyboard and a11y

Focus order (DOM order = visual): header → `+ Ny session` → session list (Styrda, Observerade) →
toolbar (Graf/Lista toggle, mode select, Stoppa) → graph container or node list → `#log` (when open)
→ chat (tool `summary` elements) → permission cards (`Tillåt`, `Neka` per card) → textarea → `Skicka`.

- Session list: `<nav aria-label="Sessioner">`, each `.sess` is a `<button aria-current="true">` when
  selected; ArrowUp/Down move focus between session buttons (roving), Enter selects.
- Graph is a canvas, so: container `#graph` has `role=img` and a live-updated `aria-label`
  `"Agentgraf: 5 agenter, 2 kör, 1 väntar på behörighet. Byt till Lista för tangentbord."`.
- **Node list** (keyboard/screen-reader alternative, the `Lista` view): `<ol aria-label="Agenter">`
  grouped by wave (`<li><h3>Wave 1 · design</h3><ol>…`). Each item is a `<button>` with text
  `{type} — {model} — {statusSv} — {n} verktyg — {tok}` and, if any, `dispatchad av lead: {description}`.
  Enter/Space opens the log panel. Same status prefixes (▶ ⏸ ✓ ✕) as the graph. Toggle `Graf|Lista`
  is two `<button aria-pressed>`; shortcut `Alt+L` toggles; choice persisted in localStorage.
- Global keys: `Esc` closes the log panel (or the Ny session form); `/` focuses the prompt when focus is
  not in a text field; `Alt+L` view toggle. No shortcut can allow a permission (prevents accidental grants);
  Enter in the textarea never activates a card.
- Live regions:
  - `#chat` has `role=log aria-live=off` (token streaming would flood). A separate
    `<div id=sr-chat class=sr-only aria-live=polite>` receives one message per completed assistant
    turn: `"Svar klart: {first 200 chars}"`; and session-end banners.
  - `#perms` has `aria-live=assertive aria-relevant=additions`; each new card announces
    `"Behörighet krävs: {tool} från {agent}"` (the card is `role=group aria-labelledby` its heading).
    Focus is NOT moved automatically. Sidebar pink pill also covers non-selected sessions.
  - Connection status (`.live`) text has `role=status`.
- Hit targets ≥32x32 (exceeds WCAG 2.2 AA 24px). Status is never color-only (prefix glyph + word +
  border style). `<html lang="sv">`. All icon-only buttons have `aria-label`.

## 6. Reduced motion

`const rm = matchMedia('(prefers-reduced-motion: reduce)')`, listen for `change`.
- Pulse interval not started; running nodes get static `border-width:3` (no `transition-*`).
- `cy` viewport changes use no `animate`; fit is instant.
- CSS: `@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}}`
  → v1 `.live i` pulse static, log panel appears without slide, streaming caret static, chat scroll `behavior:auto`.

## 7. Empty / loading / error states

| Where | State | Content |
|---|---|---|
| App | connecting | `.live` amber `ansluter…`; main shows v1 `.empty` `väntar på data…` |
| App | disconnected | `.live.off` `frånkopplad — försöker igen…` (retry 1s→2s→5s cap); prompt + buttons disabled, placeholder `Ingen anslutning` |
| App | 401/403 token | full main `.empty` in `--red`: `Ogiltig token. Starta om appen via startaren.`; no retry loop |
| Sidebar | no sessions | `Inga sessioner än. Starta en med + Ny session.` (`--muted`) |
| Main | no session selected | `.empty`: `Välj en session till vänster eller skapa en ny.` |
| Graph | session loading | lead node placeholder with label `laddar…`, no edges |
| Graph | lead only | lead node + centred hint in `#graph` overlay `Inga subagenter än` (`--muted`, `pointer-events:none`) |
| Graph | no `phase.json` | no wave groups (not an error, no message) |
| Node list | empty | `Inga agenter än.` |
| Chat | new driven session | `Skriv en prompt nedan för att börja.` |
| Chat | error from backend | inline red line `✕ Fel: {message}` + `role=alert` once |
| Log panel | no events | `Ingen logg än.` ; load error: `Kunde inte läsa loggen.` + `Försök igen` button |
| Permission | request failed | card stays, buttons re-enabled, line `Kunde inte skicka svaret — försök igen` (`--red`) |
| Fortsätt här | resume failed | inline red text next to button; button re-enabled |

## 8. ASCII mockup (1400x900)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ // agent monitor · claude-dev-team   ● live                                    14:02:31  │
├────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ [+ Ny session]     │ fix-auth  ~/projects/app         [Graf|Lista] [Standard ▾] [Stoppa] │
│ STYRDA             ├───────────────────────────────────────────────┬─────────────────────┤
│ ┌────────────────┐ │   ┌ WAVE 0 · DESIGN ┐  ┌ WAVE 1 · BUILD ──────┐│ frontend-engineer ✕ │
│ │● fix-auth      │ │   │┌──────────────┐ │  │┌───────────────────┐ ││ sonnet 4.5 · kör    │
│ │ styrd ⏸behör.  │ │ ┌─┼▶ ui-ux-eng.  │ │  ││▶ frontend-engineer│ ││ 14 verktyg · 12.3k  │
│ └────────────────┘ │ │ ││ opus · klar ✓│ │  ││ sonnet · kör      │ ││─────────────────────│
│ OBSERVERADE        │ │ │└──────────────┘ │  │└───────────────────┘ ││ > Bygg sidebar…     │
│ ┌────────────────┐ │┌┴───┐dispatch───────┼──┼─▶┌─────────────────┐ ││ ⚙ Read · index.html │
│ │○ term-session  │ ││lead│◀- - handback -┼  ││⏸ qa-engineer     │ ││ ⚙ Edit · app.js     │
│ │ observerad     │ │└────┘               │  ││ väntar på behör. │ ││ Jag lägger till…▍   │
│ └────────────────┘ │                     └  │└─────────────────┘ ││                     │
│                    ├───────────────────────────────────────────────┴─────────────────────┤
│                    │ > /cdt:orchestration fixa auth-buggen                               │
│                    │ Jag börjar med att triagera…                                        │
│                    │ ▸ ⚙ Bash · git status                                               │
│                    ├─────────────────────────────────────────────────────────────────────┤
│                    │ ┌ Behörighet krävs · Bash ──────────── qa-engineer ───────────────┐ │
│                    │ │ npm test -- --run                          [Tillåt]  [Neka]     │ │
│                    │ └─────────────────────────────────────────────────────────────────┘ │
│                    │ [Skriv en prompt eller /kommando …                      ] [Skicka]  │
└────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

Out of scope (YAGNI): resizable splitter between graph and chat, minimap, node drag, themes, light mode.
