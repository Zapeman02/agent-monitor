import http.client, os, shutil, signal, socket, subprocess, sys, tempfile, threading, time, http.server
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__)); PK = os.path.join(HERE, "packaging")
sys.path.insert(0, HERE)
import server

tmp = tempfile.mkdtemp()
# PATH without notify-send (no desktop popups) but with ss
bindir = os.path.join(tmp, "bin"); os.mkdir(bindir)
os.symlink(shutil.which("ss"), os.path.join(bindir, "ss"))


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def launch(port, cfg, **extra):
    env = {**os.environ, "AM_PORT": str(port), "AM_CONFIG_DIR": cfg, "AM_STATE_DIR": os.path.join(tmp, "state"),
           "AM_NO_SYSTEMD": "1", "AM_REPO": HERE, "PATH": bindir, **extra}
    return subprocess.run([sys.executable, os.path.join(PK, "agent-monitor"), "--print-url"], env=env, capture_output=True, text=True, timeout=30)


def login_and_state(port, url):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    path = url.split(str(port), 1)[1]
    c.request("GET", path); r = c.getresponse(); r.read()
    assert r.status == 303, r.status
    cookie = r.getheader("Set-Cookie").split(";")[0]; assert cookie.startswith("am=")
    c.close(); c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", "/api/state", headers={"Cookie": cookie}); r = c.getresponse(); r.read()
    assert r.status == 200, r.status
    return cookie[3:]

# (a) our server already running
cfg = os.path.join(tmp, "cfgA"); httpd, tok = server.make_server(0, cfg)
port = httpd.server_address[1]; threading.Thread(target=httpd.serve_forever, daemon=True).start()
r = launch(port, cfg); assert r.returncode == 0, r.stderr
url = r.stdout.strip(); assert url.startswith(f"http://127.0.0.1:{port}/login?once="), url
assert tok not in r.stdout + r.stderr and tok not in url
assert login_and_state(port, url) == tok
httpd.shutdown(); httpd.server_close()

# (b) nothing listening -> launcher starts server.py detached
port = free_port(); cfg = os.path.join(tmp, "cfgB")
try:
    r = launch(port, cfg); assert r.returncode == 0, r.stderr
    tok = open(os.path.join(cfg, "token")).read().strip()
    assert tok not in r.stdout + r.stderr
    login_and_state(port, r.stdout.strip())
    assert os.path.exists(os.path.join(tmp, "state", "server.log"))
finally:  # kill only the server we spawned (identified by our unique config dir in its environ)
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                if f"AM_CONFIG_DIR={cfg}".encode() in open(f"/proc/{p}/environ", "rb").read().split(b"\0") and b"server.py" in open(f"/proc/{p}/cmdline", "rb").read():
                    os.kill(int(p), signal.SIGTERM)
            except OSError: pass

# (c) port held by something that is not us
class Dummy(http.server.BaseHTTPRequestHandler):
    def do_POST(self): self.send_response(404); self.end_headers()
    def log_message(self, *a): pass
port = free_port(); d = http.server.HTTPServer(("127.0.0.1", port), Dummy)
threading.Thread(target=d.serve_forever, daemon=True).start()
r = launch(port, os.path.join(tmp, "cfgA"))
assert r.returncode == 1 and "is in use by another process" in r.stderr and str(port) in r.stderr, (r.returncode, r.stderr)
seen = []
Dummy.do_POST = lambda self: (seen.append(self.headers.get("X-AM-Token")), self.send_response(404), self.end_headers())
# (d) listener owned by us passes the uid check (reaches the token POST); a foreign uid never gets the token
r = launch(port, os.path.join(tmp, "cfgA"))
assert "another process" in r.stderr and seen, (r.stderr, seen)
seen.clear()
fake = os.path.join(tmp, "net_tcp")
open(fake, "w").write("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
                      f"   0: 0100007F:{port:04X} 00000000:0000 0A 00000000:00000000 00:00000000 00000000 {os.getuid() + 1}        0 1 1\n")
r = launch(port, os.path.join(tmp, "cfgA"), AM_PROC_NET_TCP=fake)
assert r.returncode == 1 and "another user's process" in r.stderr and not seen, (r.stderr, seen)
d.shutdown()

# static checks
ET.parse(os.path.join(PK, "agent-monitor.svg"))
sub = lambda f, **kv: open(os.path.join(PK, f)).read().replace("@BIN@", "/bin/true").replace("@REPO@", HERE)
open(os.path.join(tmp, "agent-monitor.desktop"), "w").write(sub("agent-monitor.desktop"))
open(os.path.join(tmp, "agent-monitor.service"), "w").write(sub("agent-monitor.service"))
if shutil.which("desktop-file-validate"):
    r = subprocess.run(["desktop-file-validate", os.path.join(tmp, "agent-monitor.desktop")], capture_output=True, text=True)
    assert r.returncode == 0 and not r.stdout + r.stderr, r.stdout + r.stderr
if shutil.which("systemd-analyze"):
    r = subprocess.run(["systemd-analyze", "--user", "verify", os.path.join(tmp, "agent-monitor.service")], capture_output=True, text=True)
    assert r.returncode == 0 and not r.stdout + r.stderr, r.stdout + r.stderr
# claude must resolve under the unit's PATH
unitpath = [l for l in sub("agent-monitor.service").splitlines() if l.startswith("Environment=PATH=")][0].split("=", 2)[2].replace("%h", os.path.expanduser("~"))
if shutil.which("claude"):
    c = shutil.which("claude", path=unitpath); assert c, unitpath
    # a mise wrapper script ("mise use -g claude") hangs/loops under systemd; the unit must hit the real binary
    with open(c, "rb") as f: assert b"mise use" not in f.read(4096), c

# install.sh --dry-run: lists targets, touches nothing
home = os.path.join(tmp, "home"); os.mkdir(home)
r = subprocess.run(["sh", os.path.join(PK, "install.sh"), "--dry-run"], env={**os.environ, "HOME": home}, capture_output=True, text=True)
assert r.returncode == 0, r.stderr
for t in (".local/bin/agent-monitor", ".local/share/applications/agent-monitor.desktop", "hicolor/scalable/apps/agent-monitor.svg",
          ".config/systemd/user/agent-monitor.service", "enable agent-monitor.service", "restart agent-monitor.service", "SUPER+ALT+A"):
    assert t in r.stdout, t
assert os.listdir(home) == [], os.listdir(home)
# (e) real install into a temp HOME with a stub systemctl: REPO with spaces/&/| survives; port-busy stops
weird = os.path.join(tmp, "re po & x|y"); os.makedirs(os.path.join(weird, "packaging"))
for f in os.listdir(PK): shutil.copy(os.path.join(PK, f), os.path.join(weird, "packaging", f))
stub = os.path.join(tmp, "stub"); os.mkdir(stub)
open(os.path.join(stub, "systemctl"), "w").write('#!/bin/sh\necho "systemctl $*" >> "$HOME/calls"\n[ "$3" = show ] && echo 0\nexit 0\n')
os.chmod(os.path.join(stub, "systemctl"), 0o755)
ih = os.path.join(tmp, "ihome"); os.mkdir(ih)
ienv = {**os.environ, "HOME": ih, "PATH": stub + ":" + os.environ["PATH"], "AM_PORT": str(free_port())}
r = subprocess.run(["sh", os.path.join(weird, "packaging", "install.sh")], env=ienv, capture_output=True, text=True)
assert r.returncode == 0, r.stderr
assert f'REPO = "{weird}"' in open(os.path.join(ih, ".local/bin/agent-monitor")).read()
assert f"ExecStart=/usr/bin/python3 {weird}/server.py" in open(os.path.join(ih, ".config/systemd/user/agent-monitor.service")).read()
calls = open(os.path.join(ih, "calls")).read(); assert "enable agent-monitor.service" in calls and "restart agent-monitor.service" in calls and "--now" not in calls, calls
bp = free_port(); busy = subprocess.Popen([sys.executable, "-m", "http.server", str(bp), "--bind", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(1)
    r = subprocess.run(["sh", os.path.join(weird, "packaging", "install.sh")], env={**ienv, "AM_PORT": str(bp)}, capture_output=True, text=True)
    assert r.returncode == 1 and f"pid {busy.pid}" in r.stderr and "http.server" in r.stderr, (r.returncode, r.stderr)
    assert busy.poll() is None
finally:
    busy.terminate()
print("ok")
