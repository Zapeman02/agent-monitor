#!/bin/sh
# Install/uninstall Agent Monitor desktop integration for the current user.
# Usage: install.sh [--dry-run] [--uninstall]
set -eu
DRY=0; UNINSTALL=0
for a in "$@"; do case $a in --dry-run) DRY=1;; --uninstall) UNINSTALL=1;; *) echo "unknown flag: $a" >&2; exit 2;; esac; done
SRC=$(cd "$(dirname "$0")" && pwd); REPO=$(dirname "$SRC")
BIN=$HOME/.local/bin/agent-monitor
APP=$HOME/.local/share/applications/agent-monitor.desktop
ICON=$HOME/.local/share/icons/hicolor/scalable/apps/agent-monitor.svg
UNIT=$HOME/.config/systemd/user/agent-monitor.service
HYPR=$HOME/.config/hypr; HFILE=$HYPR/agent-monitor.lua; HMAIN=$HYPR/hyprland.lua
REQ='require("hypr.agent-monitor")'
# The GTK window's Wayland app_id (prgname in the launcher) is the Hyprland class; rules are regexes.
WCLASS='agent-monitor'
PORT=${AM_PORT:-7777}
# Substitute @TOKEN@-style placeholders without sed: values go via env, so / & | \ and spaces are literal.
subst() { S_FROM=$1 S_TO=$2 python3 -c 'import os,sys; sys.stdout.write(sys.stdin.read().replace(os.environ["S_FROM"], os.environ["S_TO"]))'; }

run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }
note() { echo "# $*"; }

if [ "$UNINSTALL" = 1 ]; then
  run systemctl --user disable --now agent-monitor.service || true
  run rm -f "$BIN" "$APP" "$ICON" "$UNIT" "$HFILE"
  run systemctl --user daemon-reload
  if [ -f "$HMAIN" ] && grep -qF "$REQ" "$HMAIN"; then
    run sed -i "\|^$(printf '%s' "$REQ" | sed 's/[][\.*^$/]/\\&/g')\$|d" "$HMAIN"
  fi
  exit 0
fi

run mkdir -p "$(dirname "$BIN")" "$(dirname "$APP")" "$(dirname "$ICON")" "$(dirname "$UNIT")"
echo "+ install launcher -> $BIN"
[ "$DRY" = 1 ] || { subst 'REPO = ""' "REPO = \"$REPO\"" < "$SRC/agent-monitor" > "$BIN"; chmod 0755 "$BIN"; }
echo "+ install desktop entry -> $APP"
[ "$DRY" = 1 ] || subst @BIN@ "$BIN" < "$SRC/agent-monitor.desktop" > "$APP"
echo "+ install icon -> $ICON"
[ "$DRY" = 1 ] || cp "$SRC/agent-monitor.svg" "$ICON"
echo "+ install unit -> $UNIT"
[ "$DRY" = 1 ] || subst @REPO@ "$REPO" < "$SRC/agent-monitor.service" > "$UNIT"
run systemctl --user daemon-reload
# Port busy with something that is not our unit? Report and stop (never kill it here).
UNITPID=$(systemctl --user show -p MainPID --value agent-monitor.service 2>/dev/null || echo 0)
BPID=$(ss -ltnpH "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -n1)
if [ -n "$BPID" ] && [ "$BPID" != "$UNITPID" ]; then
  echo "port $PORT is in use by pid $BPID (not agent-monitor.service): $(tr '\0' ' ' < "/proc/$BPID/cmdline" 2>/dev/null)" >&2
  if [ "$DRY" = 1 ]; then note "dry-run: would stop here — free the port and run again"; else
    echo "Stop that process manually and run install.sh again (the script never kills it)." >&2; exit 1; fi
fi
run systemctl --user enable agent-monitor.service
run systemctl --user restart agent-monitor.service

# Hyprland (Omarchy: Lua config; personal files are require()d from hyprland.lua)
if [ ! -f "$HFILE" ] && { grep -rqE 'SUPER *\+ *ALT *\+ *A"' "$HYPR" 2>/dev/null || \
   { command -v hyprctl >/dev/null && hyprctl binds -j 2>/dev/null | python3 -c 'import json,sys; sys.exit(0 if any(b["modmask"]==72 and b["key"].lower()=="a" for b in json.load(sys.stdin)) else 1)'; }; }; then
  note "SUPER+ALT+A is already bound — skipping the Hyprland part (bind/windowrule)"
else
  echo "+ write $HFILE (bind SUPER+ALT+A, window rule for class $WCLASS)"
  if [ "$DRY" != 1 ]; then
    mkdir -p "$HYPR"
    cat > "$HFILE" <<LUA
-- Managed by agent-monitor/packaging/install.sh
o.bind("SUPER + ALT + A", "Agent Monitor", "$BIN")
o.window("^$WCLASS\$", { tag = "-default-opacity", tile = true, opacity = "1 1" })
LUA
  fi
  if [ -f "$HMAIN" ] && grep -qF "$REQ" "$HMAIN"; then :; else
    echo "+ append '$REQ' to $HMAIN"
    [ "$DRY" = 1 ] || printf '\n%s\n' "$REQ" >> "$HMAIN"
  fi
fi
