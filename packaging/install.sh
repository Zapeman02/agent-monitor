#!/bin/sh
# Install/uninstall Agent Monitor for the current macOS user.
# Usage: install.sh [--dry-run] [--uninstall]
set -eu
DRY=0; UNINSTALL=0
for a in "$@"; do case $a in --dry-run) DRY=1;; --uninstall) UNINSTALL=1;; *) echo "unknown flag: $a" >&2; exit 2;; esac; done
SRC=$(cd "$(dirname "$0")" && pwd); REPO=$(dirname "$SRC")
BIN=$HOME/.local/bin/agent-monitor
APP=$HOME/Applications/Agent\ Monitor.app
# Substitute @TOKEN@-style placeholders without sed: values go via env, so / & | \ and spaces are literal.
subst() { S_FROM=$1 S_TO=$2 python3 -c 'import os,sys; sys.stdout.write(sys.stdin.read().replace(os.environ["S_FROM"], os.environ["S_TO"]))'; }
# Plist values are XML: escape & < > first.
xml() { S_V=$1 python3 -c 'import os,sys; from xml.sax.saxutils import escape; sys.stdout.write(escape(os.environ["S_V"]))'; }

run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }

if [ "$UNINSTALL" = 1 ]; then
  run rm -rf "$BIN" "$APP"
  exit 0
fi

run mkdir -p "$(dirname "$BIN")" "$APP/Contents/MacOS" "$APP/Contents/Resources"
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

echo "# done: open 'Agent Monitor' from Spotlight/Launchpad, or run agent-monitor (the server starts on first open)"
