"""
Wizzy Bot Host — Upload & run Telegram bots live
Deploy on Render as a Web Service: python app.py
"""

import os, sys, time, threading, subprocess, signal
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wizzytechhost2025")

UPLOAD_FOLDER = "bots"
LOG_MAX_LINES = 300
PASSWORD = os.environ.get("HOST_PASSWORD", "wizzy123")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── State ──────────────────────────────────────────────────────────────────────
bots = {}   # name → { process, log_lines, restart_count, status, path, keep_alive }

# ── Process manager ───────────────────────────────────────────────────────────
def run_bot(name, path, env_vars):
    """Launch bot, capture logs, auto-restart on crash."""
    entry = bots[name]
    entry["status"] = "starting"
    env = {**os.environ, **env_vars}

    while entry.get("keep_alive", True):
        entry["restart_count"] = entry.get("restart_count", 0)
        proc = subprocess.Popen(
            [sys.executable, "-u", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
        )
        entry["process"] = proc
        entry["pid"] = proc.pid
        entry["status"] = "running"
        entry["started_at"] = time.strftime("%H:%M:%S")
        _log(name, f"[HOST] Bot started (PID {proc.pid})")

        # Stream output
        for line in proc.stdout:
            _log(name, line.rstrip())
            if not entry.get("keep_alive", True):
                break

        proc.wait()
        entry["status"] = "crashed" if entry.get("keep_alive") else "stopped"
        _log(name, f"[HOST] Process exited (code {proc.returncode})")

        if not entry.get("keep_alive", True):
            break

        entry["restart_count"] += 1
        _log(name, f"[HOST] Auto-restarting in 5s... (restart #{entry['restart_count']})")
        time.sleep(5)

    entry["status"] = "stopped"
    entry["process"] = None

def _log(name, line):
    lines = bots[name].setdefault("log_lines", [])
    lines.append(line)
    if len(lines) > LOG_MAX_LINES:
        del lines[:-LOG_MAX_LINES]


# ── HTML ───────────────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wizzy Bot Host</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#0a0c10;--panel:#111520;--border:#1e2535;
    --green:#00ff88;--red:#ff4466;--yellow:#ffcc00;--blue:#38bdf8;
    --text:#c9d1e0;--dim:#4a5568;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono',monospace;min-height:100vh}
  header{padding:24px 32px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:16px}
  header h1{font-family:'Syne',sans-serif;font-size:1.6rem;color:var(--green);letter-spacing:-1px}
  header span{font-size:.75rem;color:var(--dim);background:var(--panel);padding:4px 10px;border-radius:4px;border:1px solid var(--border)}
  .main{max-width:960px;margin:0 auto;padding:32px 16px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:24px;margin-bottom:24px}
  .card h2{font-family:'Syne',sans-serif;font-size:1rem;color:var(--blue);margin-bottom:16px;letter-spacing:.5px}
  label{display:block;font-size:.72rem;color:var(--dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:.08em}
  input[type=text],input[type=password],textarea,input[type=file]{
    width:100%;background:#0d1117;border:1px solid var(--border);border-radius:6px;
    color:var(--text);font-family:'JetBrains Mono',monospace;font-size:.82rem;
    padding:10px 12px;outline:none;transition:border .2s
  }
  input:focus,textarea:focus{border-color:var(--green)}
  textarea{resize:vertical;min-height:80px}
  .row{display:flex;gap:12px;flex-wrap:wrap}
  .row>*{flex:1;min-width:200px}
  btn,button,.btn{
    display:inline-block;padding:10px 20px;border-radius:6px;font-family:'JetBrains Mono',monospace;
    font-size:.82rem;font-weight:700;cursor:pointer;border:none;transition:all .15s;text-transform:uppercase;letter-spacing:.05em
  }
  .btn-green{background:var(--green);color:#000}
  .btn-green:hover{filter:brightness(1.15)}
  .btn-red{background:var(--red);color:#fff}
  .btn-yellow{background:var(--yellow);color:#000}
  .btn-dim{background:var(--border);color:var(--text)}
  .btn-dim:hover{background:#2a3350}
  .bot-row{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--border);flex-wrap:wrap}
  .bot-row:last-child{border-bottom:none}
  .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
  .dot-run{background:var(--green);box-shadow:0 0 8px var(--green)}
  .dot-stop{background:var(--dim)}
  .dot-crash{background:var(--red);animation:blink 1s infinite}
  @keyframes blink{50%{opacity:.2}}
  .bot-name{font-weight:700;color:#fff;flex:1;min-width:120px}
  .badge{font-size:.68rem;padding:3px 8px;border-radius:4px;background:var(--border);color:var(--dim)}
  .badge-run{background:#00ff8822;color:var(--green)}
  .badge-crash{background:#ff446622;color:var(--red)}
  .log-box{background:#060810;border:1px solid var(--border);border-radius:6px;padding:14px;font-size:.73rem;line-height:1.7;height:280px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
  .log-box .err{color:var(--red)}
  .log-box .sys{color:var(--blue)}
  .toast{position:fixed;bottom:24px;right:24px;background:var(--green);color:#000;padding:12px 20px;border-radius:8px;font-weight:700;font-size:.82rem;display:none;z-index:999}
  .err-toast{background:var(--red);color:#fff}
  #loginWrap{display:flex;align-items:center;justify-content:center;min-height:100vh}
  #loginBox{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:40px;width:100%;max-width:360px}
  #loginBox h1{font-family:'Syne',sans-serif;color:var(--green);font-size:1.4rem;margin-bottom:24px}
  #authErr{color:var(--red);font-size:.78rem;margin-top:10px;display:none}
  select{width:100%;background:#0d1117;border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:'JetBrains Mono',monospace;font-size:.82rem;padding:10px 12px;outline:none}
</style>
</head>
<body>

<!-- Login Screen -->
<div id="loginWrap">
  <div id="loginBox">
    <h1>⚡ Wizzy Bot Host</h1>
    <label>Password</label>
    <input type="password" id="pwInput" placeholder="Enter password..." onkeydown="if(event.key==='Enter')doLogin()">
    <div id="authErr">Wrong password.</div>
    <br><br>
    <button class="btn btn-green" style="width:100%" onclick="doLogin()">ENTER →</button>
  </div>
</div>

<!-- Main App -->
<div id="appWrap" style="display:none">
<header>
  <h1>⚡ Wizzy Bot Host</h1>
  <span>Telegram Bot Manager</span>
  <span id="botCount" style="margin-left:auto">0 bots</span>
</header>

<div class="main">

  <!-- Upload -->
  <div class="card">
    <h2>// DEPLOY NEW BOT</h2>
    <div class="row" style="margin-bottom:12px">
      <div>
        <label>Bot File (.py)</label>
        <input type="file" id="botFile" accept=".py">
      </div>
      <div>
        <label>Bot Name (no spaces)</label>
        <input type="text" id="botName" placeholder="my_awesome_bot">
      </div>
    </div>
    <div style="margin-bottom:12px">
      <label>Environment Variables (one per line: KEY=VALUE)</label>
      <textarea id="envVars" placeholder="BOT_TOKEN=123456:ABC\nADMIN_ID=999"></textarea>
    </div>
    <button class="btn btn-green" onclick="uploadBot()">▲ UPLOAD & START</button>
  </div>

  <!-- Bot List -->
  <div class="card">
    <h2>// RUNNING BOTS</h2>
    <div id="botList"><span style="color:var(--dim);font-size:.8rem">No bots deployed yet.</span></div>
  </div>

  <!-- Logs -->
  <div class="card" id="logCard" style="display:none">
    <h2>// LOGS — <span id="logBotName"></span></h2>
    <div class="log-box" id="logBox"></div>
    <br>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn btn-dim" onclick="refreshLogs()">↻ REFRESH</button>
      <button class="btn btn-yellow" onclick="restartBot()">↺ RESTART</button>
      <button class="btn btn-red" onclick="stopBot()">■ STOP</button>
    </div>
  </div>

</div>
</div>

<div class="toast" id="toast"></div>

<script>
let token = '';
let selectedBot = '';
let pollInterval = null;

// ── Auth ───────────────────────────────────────────────────────────────────
function doLogin(){
  const pw = document.getElementById('pwInput').value;
  fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})})
  .then(r=>r.json()).then(d=>{
    if(d.token){
      token=d.token;
      document.getElementById('loginWrap').style.display='none';
      document.getElementById('appWrap').style.display='block';
      startPolling();
    } else {
      document.getElementById('authErr').style.display='block';
    }
  });
}

// ── Upload ─────────────────────────────────────────────────────────────────
function uploadBot(){
  const file = document.getElementById('botFile').files[0];
  const name = document.getElementById('botName').value.trim().replace(/\s+/g,'_');
  const envRaw = document.getElementById('envVars').value.trim();
  if(!file){return toast('Select a .py file','err')}
  if(!name){return toast('Enter a bot name','err')}
  const fd = new FormData();
  fd.append('file', file);
  fd.append('name', name);
  fd.append('env', envRaw);
  fetch('/api/upload',{method:'POST',headers:{'X-Token':token},body:fd})
  .then(r=>r.json()).then(d=>{
    if(d.ok){toast('Bot deployed! ✓'); refreshList();}
    else toast(d.error||'Upload failed','err');
  });
}

// ── List ───────────────────────────────────────────────────────────────────
function refreshList(){
  fetch('/api/bots',{headers:{'X-Token':token}}).then(r=>r.json()).then(data=>{
    const el = document.getElementById('botList');
    document.getElementById('botCount').textContent = data.length + ' bot'+(data.length!==1?'s':'');
    if(!data.length){el.innerHTML='<span style="color:var(--dim);font-size:.8rem">No bots deployed yet.</span>';return;}
    el.innerHTML = data.map(b=>`
      <div class="bot-row">
        <div class="dot dot-${b.status==='running'?'run':b.status==='crashed'?'crash':'stop'}"></div>
        <span class="bot-name">${b.name}</span>
        <span class="badge badge-${b.status==='running'?'run':b.status==='crashed'?'crash':''}">
          ${b.status.toUpperCase()}
        </span>
        <span style="font-size:.72rem;color:var(--dim)">restarts: ${b.restart_count}</span>
        <button class="btn btn-dim" style="padding:6px 14px" onclick="viewLogs('${b.name}')">LOGS</button>
        <button class="btn btn-red" style="padding:6px 14px" onclick="deleteBot('${b.name}')">DEL</button>
      </div>`).join('');
  });
}

// ── Logs ───────────────────────────────────────────────────────────────────
function viewLogs(name){
  selectedBot=name;
  document.getElementById('logCard').style.display='block';
  document.getElementById('logBotName').textContent=name;
  refreshLogs();
  document.getElementById('logCard').scrollIntoView({behavior:'smooth'});
}

function refreshLogs(){
  if(!selectedBot)return;
  fetch(`/api/logs/${selectedBot}`,{headers:{'X-Token':token}}).then(r=>r.json()).then(d=>{
    const box=document.getElementById('logBox');
    box.innerHTML=d.lines.map(l=>{
      const cls=l.includes('[HOST]')?'sys':l.toLowerCase().includes('error')||l.includes('Traceback')?'err':'';
      return `<span class="${cls}">${escape(l)}</span>`;
    }).join('\n');
    box.scrollTop=box.scrollHeight;
  });
}

function escape(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

// ── Controls ───────────────────────────────────────────────────────────────
function restartBot(){
  fetch(`/api/restart/${selectedBot}`,{method:'POST',headers:{'X-Token':token}})
  .then(r=>r.json()).then(d=>{ toast(d.ok?'Restarting...':d.error,'err' );setTimeout(refreshLogs,2000);});
}

function stopBot(){
  fetch(`/api/stop/${selectedBot}`,{method:'POST',headers:{'X-Token':token}})
  .then(r=>r.json()).then(d=>{ toast('Stopped.'); refreshList(); });
}

function deleteBot(name){
  if(!confirm(`Delete ${name}?`))return;
  fetch(`/api/delete/${name}`,{method:'DELETE',headers:{'X-Token':token}})
  .then(r=>r.json()).then(d=>{ toast('Deleted.'); if(selectedBot===name){document.getElementById('logCard').style.display='none';selectedBot='';} refreshList(); });
}

// ── Polling ────────────────────────────────────────────────────────────────
function startPolling(){
  refreshList();
  pollInterval=setInterval(()=>{refreshList();if(selectedBot)refreshLogs();},4000);
}

// ── Toast ──────────────────────────────────────────────────────────────────
function toast(msg,type='ok'){
  const t=document.getElementById('toast');
  t.textContent=msg;
  t.className='toast'+(type==='err'?' err-toast':'');
  t.style.display='block';
  setTimeout(()=>t.style.display='none',2800);
}
</script>
</body>
</html>"""


# ── Auth helper ───────────────────────────────────────────────────────────────
import hashlib, secrets

_sessions = set()

def _auth(req):
    return req.headers.get("X-Token") in _sessions


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    if data.get("password") == PASSWORD:
        tok = secrets.token_hex(24)
        _sessions.add(tok)
        return jsonify({"token": tok})
    return jsonify({"error": "bad password"}), 403


@app.route("/api/upload", methods=["POST"])
def upload():
    if not _auth(request):
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("file")
    name = request.form.get("name", "").strip().replace(" ", "_")
    env_raw = request.form.get("env", "")

    if not file or not name:
        return jsonify({"error": "Missing file or name"}), 400

    filename = secure_filename(file.filename)
    if not filename.endswith(".py"):
        return jsonify({"error": "Only .py files allowed"}), 400

    # Stop old instance if re-deploying same name
    _stop_bot(name)

    path = os.path.join(UPLOAD_FOLDER, f"{name}.py")
    file.save(path)

    # Parse env vars
    env_vars = {}
    for line in env_raw.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env_vars[k.strip()] = v.strip()

    bots[name] = {
        "name": name,
        "path": path,
        "log_lines": [],
        "restart_count": 0,
        "keep_alive": True,
        "status": "starting",
        "process": None,
        "pid": None,
        "started_at": None,
        "env_vars": env_vars,
    }

    t = threading.Thread(target=run_bot, args=(name, path, env_vars), daemon=True)
    t.start()

    return jsonify({"ok": True, "name": name})


@app.route("/api/bots")
def list_bots():
    if not _auth(request):
        return jsonify([])
    return jsonify([
        {
            "name": n,
            "status": e.get("status", "unknown"),
            "restart_count": e.get("restart_count", 0),
            "pid": e.get("pid"),
            "started_at": e.get("started_at"),
        }
        for n, e in bots.items()
    ])


@app.route("/api/logs/<name>")
def get_logs(name):
    if not _auth(request):
        return jsonify({"lines": []})
    entry = bots.get(name)
    if not entry:
        return jsonify({"lines": ["Bot not found"]})
    return jsonify({"lines": entry.get("log_lines", [])})


@app.route("/api/restart/<name>", methods=["POST"])
def restart(name):
    if not _auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    entry = bots.get(name)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    _stop_bot(name)
    time.sleep(1)
    entry["keep_alive"] = True
    entry["status"] = "starting"
    t = threading.Thread(target=run_bot, args=(name, entry["path"], entry.get("env_vars", {})), daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.route("/api/stop/<name>", methods=["POST"])
def stop(name):
    if not _auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    _stop_bot(name)
    return jsonify({"ok": True})


@app.route("/api/delete/<name>", methods=["DELETE"])
def delete(name):
    if not _auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    _stop_bot(name)
    entry = bots.pop(name, None)
    if entry:
        try:
            os.remove(entry["path"])
        except Exception:
            pass
    return jsonify({"ok": True})


def _stop_bot(name):
    entry = bots.get(name)
    if not entry:
        return
    entry["keep_alive"] = False
    proc = entry.get("process")
    if proc and proc.poll() is None:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    entry["status"] = "stopped"
    entry["process"] = None


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[WizzyHost] Starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
