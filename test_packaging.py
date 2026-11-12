import http.client, os, shutil, signal, socket, subprocess, sys, tempfile, threading, time, http.server
import plistlib, xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__)); PK = os.path.join(HERE, "packaging")
sys.path.insert(0, HERE)
import server

tmp = tempfile.mkdtemp()
# PATH without osascript (no notification popups) but with lsof
bindir = os.path.join(tmp, "bin"); os.mkdir(bindir)
os.symlink(shutil.which("lsof"), os.path.join(bindir, "lsof"))


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def launch(port, cfg, **extra):
    env = {**os.environ, "AM_PORT": str(port), "AM_CONFIG_DIR": cfg, "AM_STATE_DIR": os.path.join(tmp, "state"),
           "AM_REPO": HERE, "PATH": bindir, **extra}
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
finally:  # kill only the server we spawned (the listener on our fresh port)
    out = subprocess.run(["lsof", "-nP", "-t", f"-iTCP@127.0.0.1:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    for p in out.split():
        try: os.kill(int(p), signal.SIGTERM)
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
fake = os.path.join(tmp, "fake_lsof")
open(fake, "w").write(f'#!/bin/sh\necho p1\necho u{os.getuid() + 1}\n'); os.chmod(fake, 0o755)
r = launch(port, os.path.join(tmp, "cfgA"), AM_LSOF=fake)
assert r.returncode == 1 and "another user's process" in r.stderr and not seen, (r.stderr, seen)
d.shutdown()

# static checks
ET.parse(os.path.join(PK, "agent-monitor.svg"))
r = subprocess.run(["plutil", "-lint", os.path.join(PK, "Info.plist")], capture_output=True, text=True); assert r.returncode == 0, r.stdout

# install.sh --dry-run: lists targets, touches nothing
home = os.path.join(tmp, "home"); os.mkdir(home)
r = subprocess.run(["sh", os.path.join(PK, "install.sh"), "--dry-run"], env={**os.environ, "HOME": home}, capture_output=True, text=True)
assert r.returncode == 0, r.stderr
for t in (".local/bin/agent-monitor", "Applications/Agent Monitor.app"):
    assert t in r.stdout, t
assert os.listdir(home) == [], os.listdir(home)
# (e) real install into a temp HOME with a stub swiftc: REPO with spaces/&/| survives
weird = os.path.join(tmp, "re po & x|y"); os.makedirs(os.path.join(weird, "packaging"))
for f in os.listdir(PK): shutil.copy(os.path.join(PK, f), os.path.join(weird, "packaging", f))
stub = os.path.join(tmp, "stub"); os.mkdir(stub)
open(os.path.join(stub, "swiftc"), "w").write('#!/bin/sh\n: > "$3"\n')  # swiftc -O -o <out> <src>
os.chmod(os.path.join(stub, "swiftc"), 0o755)
ih = os.path.join(tmp, "ihome"); os.mkdir(ih)
ienv = {**os.environ, "HOME": ih, "PATH": stub + ":" + os.environ["PATH"]}
r = subprocess.run(["sh", os.path.join(weird, "packaging", "install.sh")], env=ienv, capture_output=True, text=True)
assert r.returncode == 0, r.stderr
assert f'REPO = "{weird}"' in open(os.path.join(ih, ".local/bin/agent-monitor")).read()
assert plistlib.loads(open(os.path.join(ih, "Applications/Agent Monitor.app/Contents/Info.plist"), "rb").read())["AMLauncher"] == os.path.join(ih, ".local/bin/agent-monitor")
print("ok")
