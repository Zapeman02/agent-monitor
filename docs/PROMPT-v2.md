/cdt:orchestration FULL: Bygg Agent Monitor v2 enligt planen i ~/projects/agent-monitor/docs/v2-plan.md. Kör hela ledet: Wave 0 → Wave 1 → Task Loop → Wave 2 → ship, en milstolpe i taget (M1 → M4), med en liten commit per milstolpe.

## Kontext
- Projektet ligger i `~/projects/agent-monitor`: `server.py` (Python stdlib, läser `~/.claude/projects/**/*.jsonl` + `subagents/` + `<cwd>/.claude/runtime/phase.json` + `~/.claude/claude-dev-team.db`), `index.html` (mörk node-graf-UI) och `test_server.py`. Läs alla tre först.
- Det är mitt personliga projekt. Kör `git init` om det behövs, committa per milstolpe och lägg ingen Claude-attribution eller Co-Authored-By i commits.
- Linux-miljö: Omarchy (Arch + Hyprland), `/usr/bin/chromium`, Python 3, Node 26, Claude Code 2.1.319.

## Målet i en mening
Ett eget Linux-fönster där jag skriver prompter som i Claude Code (även `/cdt:orchestration …`) och samtidigt ser en **live-graf** över hur leaden och subagenterna jobbar med varandra: dispatch, handback, waves och status. Jag kan klicka på en nod för att se dess logg och tillåta eller neka behörighetsfrågor i UI:t.

## Verifiera först (Wave 0, architect, utgå inte från minnet)
1. Hur appen styr Claude Code: Claude Agent SDK för Python (`claude-agent-sdk`) eller `claude -p --input-format stream-json --output-format stream-json --verbose`. Ta reda på vilket sätt som **laddar mina user/project settings, CLAUDE.md, hooks och plugins**, så att min CDT-harness körs. `--bare` får aldrig användas. Använd context7 / Agent SDK-dokumentationen / `claude --help`.
2. Hur subagent-händelser syns i strömmen (t.ex. `parent_tool_use_id`) och hur de kopplas till noder i grafen.
3. Hur behörighetsfrågor går till appen (`--permission-prompts host` / `can_use_tool`) och hur ett avbrott fungerar.
4. Hur en session fortsätts (`--resume <id>`).
Skriv ner svaren med källa i `docs/architecture-v2.md` innan något byggs.

## Krav
- **Graf (M1):** noder för lead och subagenter, med typ, modell, status (kör/klar/väntar på behörighet), antal verktygsanrop och tokens om de finns. Kanterna visar dispatch (lead → agent, med beskrivning) och handback. Waves läses från `phase.json` och ritas som kolumner eller grupper. Löpande noder pulserar (inte med reduced motion). Klick på en nod öppnar en panel med agentens hela logg. Cytoscape.js (eller motsvarande) ska ligga **lokalt** i repot, inte på ett CDN.
- **Prompt och chatt (M2):** en prompt-ruta med historik (pil upp) och slash-kommandon som skickas oförändrade. Svaren strömmar i chatten, verktygsanrop kan fällas ihop, och man kan starta en ny session eller fortsätta en befintlig. Sessioner från terminalen (v1-läget) syns fortfarande read-only.
- **Kontroll (M3):** tillåt/neka-kort för behörighetsfrågor, en avbryt-knapp och val av permission mode per session. Det får inte finnas något sätt att slå av alla behörigheter från UI:t.
- **Linux-app (M4):** en `agent-monitor`-startare som startar backend om den inte redan körs och öppnar `chromium --app=http://127.0.0.1:<port>/`. Dessutom en `.desktop`-fil i `~/.local/share/applications`, en ikon och en systemd `--user`-tjänst. Använd omarchy-skillen för en tangentbindning (förslag SUPER+ALT+A) och en Hyprland-fönsterregel.

## Säkerhet (risk floor, full mandate och security-reviewer med veto)
Appen kör kommandon på min dator. Följande gäller:
- Servern lyssnar bara på 127.0.0.1.
- En slumpad token skapas per start och sparas med 0600. Alla API- och ström-anrop kräver den.
- `Host`- och `Origin`-kontroll mot DNS-rebinding och CSRF. Ingen CORS.
- Inga hemligheter i loggar.
- Transcripts skickas aldrig ut.
- Testa uttryckligen att en främmande origin **inte** kan skicka en prompt.

## Tester (via cdt-verify)
- Enhetstester för transcript-parsern och för reducern som bygger grafen från ström-händelser, mot en inspelad fixture från en riktig T2-session.
- E2E i headless Chromium med en **fejkad `claude`-binär** som spelar upp inspelad stream-json, så att testerna inte kostar tokens. Täck prompt → chatt → noder som dyker upp → behörighetskort → tillåt → handback.
- Säkerhetstester för token, Host och Origin.
- Behåll `test_server.py` grön.

## Done när
Alla fyra milstolparna är klara och gröna via `cdt-verify`. Wave 2 (code-reviewer + security-reviewer + ui-ux-engineer) har inga öppna fynd på medium eller högre. Jag kan öppna appen från app-menyn, skriva `/cdt:orchestration <något litet>` och se agenterna växa fram i grafen. Rapportera med skärmdumpar.
