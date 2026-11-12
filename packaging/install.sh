#!/bin/sh
# Install/uninstall Agent Monitor for the current macOS user.
# Usage: install.sh [--dry-run] [--uninstall]
set -eu
DRY=0; UNINSTALL=0
for a in "$@"; do case $a in --dry-run) DRY=1;; --uninstall) UNINSTALL=1;; *) echo "unknown flag: $a" >&2; exit 2;; esac; done
SRC=$(cd "$(dirname "$0")" && pwd); REPO=$(dirname "$SRC")
BIN=$HOME/.local/bin/agent-monitor
APP=$HOME/Applications/Agent\ Monitor.app
LABEL=local.agentmonitor
PLIST=$HOME/Library/LaunchAgents/$LABEL.plist
STATE=$HOME/.local/state/agent-monitor
DOMAIN=gui/$(id -u)
PORT=${AM_PORT:-7777}
PYTHON=$(command -v python3)
# Substitute @TOKEN@-style placeholders without sed: values go via env, so / & | \ and spaces are literal.
subst() { S_FROM=$1 S_TO=$2 python3 -c 'import os,sys; sys.stdout.write(sys.stdin.read().replace(os.environ["S_FROM"], os.environ["S_TO"]))'; }
# Plist values are XML: escape & < > first.
xml() { S_V=$1 python3 -c 'import os,sys; from xml.sax.saxutils import escape; sys.stdout.write(escape(os.environ["S_V"]))'; }

run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }

if [ "$UNINSTALL" = 1 ]; then
  run launchctl bootout "$DOMAIN/$LABEL" || true
  run rm -rf "$BIN" "$APP" "$PLIST"
  exit 0
fi

run mkdir -p "$(dirname "$BIN")" "$APP/Contents/MacOS" "$APP/Contents/Resources" "$(dirname "$PLIST")" "$STATE"
echo "+ install launcher -> $BIN"
[ "$DRY" = 1 ] || { subst 'REPO = ""' "REPO = \"$REPO\"" < "$SRC/agent-monitor" > "$BIN"; chmod 0755 "$BIN"; }

echo "+ build app -> $APP"
if [ "$DRY" != 1 ]; then
  command -v swiftc >/dev/null || { echo "swiftc not found: run xcode-select --install" >&2; exit 1; }
  swiftc -O -o "$APP/Contents/MacOS/AgentMonitor" "$SRC/AgentMonitor.swift"
  subst @BIN@ "$(xml "$BIN")" < "$SRC/Info.plist" > "$APP/Contents/Info.plist"
  # icon: best effort, the app works without it
  T=$(mktemp -d)
  if qlmanage -t -s 1024 -o "$T" "$SRC/agent-monitor.svg" >/dev/null 2>&1; then
    sips -s format icns "$T/agent-monitor.svg.png" --out "$APP/Contents/Resources/AgentMonitor.icns" >/dev/null 2>&1 || true
  fi
  rm -rf "$T"
fi

echo "+ install launch agent -> $PLIST"
[ "$DRY" = 1 ] || subst @REPO@ "$(xml "$REPO")" < "$SRC/$LABEL.plist" | subst @HOME@ "$(xml "$HOME")" \
  | subst @PYTHON@ "$(xml "$PYTHON")" | subst @PORT@ "$PORT" > "$PLIST"

# Stop our own server first, so a busy port afterwards is someone else's.
run launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
BPID=$(lsof -nP -iTCP@127.0.0.1:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true)
if [ -n "$BPID" ]; then
  echo "port $PORT is in use by pid $BPID: $(ps -p "$BPID" -o command= 2>/dev/null)" >&2
  if [ "$DRY" = 1 ]; then echo "# dry-run: would stop here — free the port and run again"; else
    echo "Stop that process manually and run install.sh again (the script never kills it)." >&2; exit 1; fi
fi
run launchctl bootstrap "$DOMAIN" "$PLIST"
echo "# done: open 'Agent Monitor' from Spotlight/Launchpad, or run agent-monitor"
