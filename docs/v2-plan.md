# Agent Monitor v2: plan

## Vision
Monitorn blir ett eget Linux-fönster som du kan använda **som Claude Code**. Längst ner skriver du en prompt
(även `/cdt:orchestration …`). I mitten ser du **en graf** över hur agenterna jobbar med varandra:
leaden, subagenter, waves, vem som dispatchade vem och vem som lämnade tillbaka vad. Allt sker live.
Klickar du på en nod får du agentens hela logg.

## Hur det fungerar (tekniskt)
```
┌──────────── Linux-fönster (chromium --app) ────────────┐
│ sessioner │        GRAF (lead → agenter, waves)        │
│           │  ◉ lead ──dispatch──▶ ◉ frontend-engineer   │
│  ● live   │        └─dispatch──▶ ◉ qa-engineer          │
│  ○ idle   ├─────────────────────────────────────────────┤
│           │ chatt-ström (som Claude Code) + tillåt/neka │
│           │ > prompt-ruta ______________________ [stop] │
└───────────┴─────────────────────────────────────────────┘
        ▲ SSE/WebSocket (token-skyddad, bara 127.0.0.1)
┌───────┴────────────────────────────────────────────────┐
│ backend (Python, utbyggd server.py)                    │
│  - "driven" sessioner: Claude Agent SDK / claude -p    │
│    stream-json, med dina settings (CLAUDE.md, hooks,   │
│    plugins = din CDT-harness). ALDRIG --bare.          │
│  - "observerade" sessioner: läser transcripts som v1   │
│    (terminalsessioner du kör vid sidan av)             │
│  - behörighetsfrågor → UI-kort (tillåt/neka)           │
└────────────────────────────────────────────────────────┘
```

## Milstolpar (en liten PR per milstolpe)
| # | Milstolpe | Klart när |
|---|-----------|-----------|
| M1 | **Grafvy** på befintlig observe-data: noder för lead och subagenter, kanter för dispatch och handback, kolumner per wave från `phase.json`, pulserande nod när den kör, klick ger en loggpanel | Grafen visar en riktig inspelad T2-session korrekt (fixture-test) |
| M2 | **Prompt-fönster**: starta och fortsätta sessioner från appen, strömmande svar, slash-kommandon går igenom | En prompt i UI:t ger svar i chatten, och subagent-noder dyker upp live (testas med en fejkad `claude`) |
| M3 | **Behörigheter och kontroll**: tillåt/neka-kort, avbryt-knapp, välj permission mode per session | Ett verktygsanrop som kräver behörighet väntar på klick och nekas korrekt |
| M4 | **Linux-app**: `.desktop`-fil, en systemd `--user`-tjänst för backend, en startare som öppnar `chromium --app`, ikon, Omarchy-tangentbindning | Appen syns i app-menyn, startar fönstret och överlever en omloggning |

## Säkerhet (risk floor: appen kör kommandon på din dator)
- Servern lyssnar bara på `127.0.0.1`.
- En slumpad **token** skapas vid varje start och sparas i `~/.config/agent-monitor/token` (0600). Varje API- och ström-anrop kräver den.
- `Host`- och `Origin`-kontroll stoppar DNS-rebinding och CSRF, så att ingen webbsida kan skicka prompter till din Claude.
- Behörighetsfrågor går **alltid** till UI:t. Det finns ingen knapp som slår av alla behörigheter.
- Transcripts är privata och skickas aldrig vidare. Inga CDN-skript i appen: grafbiblioteket ligger lokalt.

## Beslut jag tagit (ändra om du vill)
- **Python-backend**, en utbyggnad av `server.py`. Claude Agent SDK för Python om den laddar dina settings och plugins, annars `claude -p` stream-json direkt. Agenten verifierar vilket som fungerar.
- **Chromium `--app`-fönster** istället för Electron eller Tauri: inga tunga beroenden och samma HTML. Tauri kan bli v3.
- **Cytoscape.js** för grafen, vendrad lokalt. Den klarar layout och klick utan egen fysikmotor.
- **Observerade sessioner** från v1 behålls. Där är grafen read-only, med en "fortsätt här"-knapp som gör `--resume`.

## Inte i v2
Flera användare, fjärråtkomst, mobil, redigering av filer i appen, egen diff-vy.
