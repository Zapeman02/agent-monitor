# Agent Monitor (macOS)

A small native macOS app for watching and steering [Claude Code](https://docs.claude.com/en/docs/claude-code) sessions live. Mac port of [willevic2002/agent-monitor](https://github.com/willevic2002/agent-monitor) (Linux).

- **Brain view:** a 3D "brain" where the lead agent and every running subagent show up as glowing neuron clusters. Next to it are a tool-call log, a chat panel, a per-agent token and cost breakdown, and permission cards with Allow and Deny buttons. Click an agent to see its own chat and tools.
- **Graph view:** the same session laid out as waves of subagents.
- **Permission modes:** *Ask me*, *Accept edits*, *Auto (runs on its own)* and *Plan mode*. You can switch modes in the middle of a run.

It runs your own `claude` CLI with your own settings, plugins and hooks. Nothing goes anywhere except `127.0.0.1`. The UI is a native Cocoa + WKWebView window, so no browser tab is involved.

## Requirements

- macOS 12+, `python3` and the Xcode Command Line Tools (`xcode-select --install`, for `swiftc`).
- The [Claude Code CLI](https://docs.claude.com/en/docs/claude-code/setup) installed and logged in. `claude --version` should work in a terminal.

## Install

```sh
git clone https://github.com/Zapeman02/agent-monitor.git
cd agent-monitor
packaging/install.sh            # --dry-run shows what it would do, --uninstall removes it
```

The installer does two things:
- adds a launcher at `~/.local/bin/agent-monitor`;
- builds `~/Applications/Agent Monitor.app` from `packaging/AgentMonitor.swift`, so it shows up in Spotlight and Launchpad.

Start it from Spotlight or with `agent-monitor`. Nothing runs at login: opening the app starts the server on `127.0.0.1:7777`, and closing it (last window or Cmd+Q) stops the server and every `claude` session it runs. Type a prompt in the chat panel on the left to start a session. Server log: `~/.local/state/agent-monitor/server.log`.

Use another port with `AM_PORT=7788 agent-monitor`. The server looks for `claude` in `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin`. If yours lives somewhere else, edit `PATH` in `packaging/agent-monitor` and run the installer again.

## Security notes

- The server only listens on `127.0.0.1`. The API needs a random token, stored at `~/.config/agent-monitor/token` with mode 0600. The window logs in with a one-time nonce.
- *Auto* mode lets Claude approve its own actions; Claude still blocks risky ones. `bypassPermissions` is intentionally not offered.

## Tests

```sh
for t in test_*.py; do python3 "$t"; done
cd tests/e2e && npm ci && node run.mjs     # needs Chromium (see tests/e2e/README.md); uses a fake claude, no tokens spent
```

## Licence

Vendored libraries: three.js (MIT) and cytoscape.js (MIT). Their licences are in `vendor/`.
