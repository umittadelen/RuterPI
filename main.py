from flask import Flask, jsonify, render_template_string, send_from_directory, request
import requests, json, os, threading, webview
from datetime import datetime, timezone

app = Flask(__name__)

# --- CONFIGURATION ---
REFRESH_DELAY = 10 
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {"stop_id": "NSR:StopPlace:58309", "stop_name": "Grefsen stadion", "max_per_quay": 10}
MAX_MINUTES = 60

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            try: 
                cfg = json.load(f)
                return {**DEFAULT_CONFIG, **cfg, "refresh_delay": REFRESH_DELAY}
            except: return {**DEFAULT_CONFIG, "refresh_delay": REFRESH_DELAY}
    return {**DEFAULT_CONFIG, "refresh_delay": REFRESH_DELAY}

def save_config(data):
    data.pop("refresh_delay", None)
    with open(CONFIG_FILE, "w") as f: json.dump(data, f, indent=2)

class Api:
    def close_app(self): os._exit(0)

# --- Frontend HTML ---
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=720, height=1280, initial-scale=1.0">
<title>Departure Board</title>
<style>
@font-face { font-family: 'TID'; src: url('/fonts/TID-Regular.woff') format('woff'); font-weight: 400; }
@font-face { font-family: 'TID'; src: url('/fonts/TID-Bold.woff') format('woff'); font-weight: 700; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background: #000; color: #fff; font-family: 'TID', Arial, sans-serif;
    overflow: hidden; width: 720px; height: 1280px; user-select: none;
}

/* Header - ALL WHITE */
.header {
    height: 75px; padding: 0 25px; border-bottom: 2px solid #fff;
    display: flex; align-items: center; justify-content: space-between; background: #000;
}
#stop-name { font-size: 24px; font-weight: 700; color: #fff; text-transform: uppercase; }
.clock { font-size: 36px; font-weight: 700; color: #fff; }
.header-actions { display: flex; align-items: center; gap: 15px; }
.refresh { font-size: 14px; color: #fff; text-align: right; font-weight: 400; }
.gear, .close-btn { background: none; border: none; cursor: pointer; padding: 5px; line-height: 1; color: #fff; }
.gear { font-size: 26px; }
.close-btn { font-size: 28px; }

/* Grid - ALL WHITE */
.platforms { display: grid; grid-template-columns: repeat(2, 1fr); grid-auto-rows: min-content; height: 1205px; width: 720px; }
.platform { border-right: 1px solid #fff; border-bottom: 1px solid #fff; display: flex; flex-direction: column; }
.platform.full-width { grid-column: span 2; border-right: none; }
.platform-label { 
    padding: 12px 15px; font-size: 14px; color: #fff; 
    text-transform: uppercase; letter-spacing: 2px; font-weight: 700;
    background: #000; border-bottom: 1px solid #fff; 
}

.row { display: grid; grid-template-columns: 55px 1fr 115px; align-items: center; padding: 18px 12px; border-bottom: 1px solid #333; gap: 10px; }
.row.soon { background: #111; }

.pill { display: flex; align-items: center; justify-content: center; width: 50px; height: 32px; border-radius: 4px; font-size: 18px; font-weight: 700; border: 1px solid #fff; }
.dest { font-size: 22px; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 400; }

/* Time Column - Pure White High Visibility */
.time-col { text-align: right; display: flex; flex-direction: column; justify-content: center; }
.countdown { 
    font-size: 26px; 
    font-weight: 700; 
    line-height: 1; 
    color: #fff; 
}
.original-time { 
    font-size: 15px; 
    color: #fff; 
    text-decoration: line-through; 
    margin-top: 6px; 
    height: 16px; 
    font-weight: 400;
    opacity: 0.7; /* Slight transparency so it doesn't compete with the main time */
}

/* Settings Overlay - ALL WHITE */
.overlay { display: none; position: absolute; inset: 0; background: rgba(0,0,0,0.98); z-index: 100; align-items: center; justify-content: center; }
.overlay.open { display: flex; }
.panel { background: #000; padding: 40px; border-radius: 0; width: 680px; display: flex; flex-direction: column; gap: 25px; border: 2px solid #fff; }
.search-input { width: 100%; padding: 18px; background: #000; color: #fff; border: 1px solid #fff; font-size: 22px; }
.btn { padding: 18px 35px; font-size: 20px; cursor: pointer; border: 1px solid #fff; background: #000; color: #fff; font-weight: 700; }
.primary { background: #fff; color: #000; border: none; }

#search-results div { border-bottom: 1px solid #fff; padding: 15px; color: #fff; }
#selected-stop-label { color: #fff; font-weight: 700; }
</style>
</head>
<body>

<div class="header">
    <span id="stop-name">---</span>
    <span id="clock" class="clock">00:00</span>
    <div class="header-actions">
        <div id="refresh" class="refresh">upd 0:00</div>
        <button class="gear" onclick="openSettings()">&#9881;</button>
        <button class="close-btn" onclick="exitApp()">&#10005;</button>
    </div>
</div>

<div class="platforms" id="board"></div>

<div class="overlay" id="overlay">
    <div class="panel">
        <h1 style="color:#fff; border-bottom: 1px solid #fff; padding-bottom: 10px;">SETTINGS</h1>
        <input class="search-input" id="stop-search" type="text" placeholder="SEARCH STOP...">
        <div id="search-results" style="max-height: 300px; overflow: auto; background: #000; border: 1px solid #fff; border-top: none;"></div>
        <div id="selected-stop-label"></div>
        <div style="color: #fff; font-size: 20px; font-weight: 700;">
            MAX ROWS: <input type="range" id="quay-slider" min="1" max="15" value="10" style="width: 250px;"> 
            <span id="quay-val">10</span>
        </div>
        <div style="display:flex; gap: 20px; justify-content: flex-end;">
            <button class="btn" onclick="closeSettings()">CANCEL</button>
            <button class="btn primary" onclick="applySettings()">APPLY</button>
        </div>
    </div>
</div>

<script>
let cfg = {};
let pendingStop = null;
let nextLoad = Date.now();

function exitApp() { if (confirm("CLOSE?")) { window.pywebview.api.close_app(); } }

async function loadCfg() {
    const res = await fetch("/config");
    cfg = await res.json();
    document.getElementById("stop-name").textContent = cfg.stop_name.toUpperCase();
    nextLoad = Date.now() + (cfg.refresh_delay * 1000);
}

async function applySettings() {
    const payload = {
        stop_id: pendingStop ? pendingStop.id : cfg.stop_id,
        stop_name: pendingStop ? pendingStop.name : cfg.stop_name,
        max_per_quay: parseInt(document.getElementById("quay-slider").value),
    };
    await fetch("/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    location.reload();
}

function tick() {
    const now = new Date();
    document.getElementById("clock").textContent = now.getHours().toString().padStart(2, '0') + ":" + now.getMinutes().toString().padStart(2, '0');
    const secs = Math.max(0, Math.ceil((nextLoad - Date.now()) / 1000));
    document.getElementById("refresh").textContent = "UPD " + Math.floor(secs / 60) + ":" + String(secs % 60).padStart(2, "0");
}

function openSettings() {
    document.getElementById("overlay").classList.add("open");
    document.getElementById("quay-slider").value = cfg.max_per_quay;
    document.getElementById("quay-val").textContent = cfg.max_per_quay;
}
function closeSettings() { document.getElementById("overlay").classList.remove("open"); }
document.getElementById("quay-slider").addEventListener("input", e => document.getElementById("quay-val").textContent = e.target.value);

document.getElementById("stop-search").addEventListener("input", async (e) => {
    const q = e.target.value; if (q.length < 3) return;
    const res = await fetch(`https://api.entur.io/geocoder/v1/autocomplete?text=${encodeURIComponent(q)}&layers=venue&size=6`);
    const data = await res.json();
    const container = document.getElementById("search-results");
    container.innerHTML = "";
    data.features.forEach(f => {
        const div = document.createElement("div");
        div.textContent = f.properties.name.toUpperCase() + " (" + (f.properties.locality || "").toUpperCase() + ")";
        div.onclick = () => {
            pendingStop = { id: f.properties.id, name: f.properties.name };
            document.getElementById("selected-stop-label").textContent = "SELECTED: " + f.properties.name.toUpperCase();
        };
        container.appendChild(div);
    });
});

const LINE_COLORS = { "25": ["#6b2fa0", "#fff"], "26": ["#003087", "#fff"], "31": ["#e8001c", "#fff"], "60": ["#007b40", "#fff"] };
function pillStyle(line) {
    const c = LINE_COLORS[line]; if (c) return `background:${c[0]};color:${c[1]}`;
    let h = 0; for (const ch of line) h = (h * 31 + ch.charCodeAt(0)) & 0xffff;
    return `background:hsl(${h % 360},65%,45%);color:#fff`;
}

async function load() {
    try {
        const res = await fetch("/data");
        const json = await res.json();
        const now = new Date();
        const board = document.getElementById("board");
        board.innerHTML = "";

        json.sort((a,b) => a.quay.localeCompare(b.quay));
        nextLoad = Date.now() + (cfg.refresh_delay * 1000);

        json.forEach((quay, index) => {
            const section = document.createElement("div");
            section.className = "platform";
            if (index === json.length - 1 && json.length % 2 !== 0) section.classList.add("full-width");
            let rowsHtml = `<div class="platform-label">PLATFORM ${quay.quay}</div>`;
            
            quay.calls.forEach(c => {
                const expected = new Date(c.expectedDepartureTime);
                const aimed = new Date(c.aimedDepartureTime);
                const mins = Math.floor((expected - now) / 60000);
                if (mins < 0) return;

                const delayMins = Math.round((expected - aimed) / 60000);
                let ct = (mins === 0) ? "NÅ" : (mins < 20) ? mins + " MIN" : expected.getHours().toString().padStart(2, '0') + ":" + expected.getMinutes().toString().padStart(2, '0');
                let originalHtml = (delayMins !== 0) ? `<div class="original-time">${aimed.getHours().toString().padStart(2, '0')}:${aimed.getMinutes().toString().padStart(2, '0')}</div>` : "";

                rowsHtml += `
                    <div class="row ${mins <= 1 ? "soon" : ""}">
                        <div><span class="pill" style="${pillStyle(c.line)}">${c.line}</span></div>
                        <div class="dest">${c.dest.toUpperCase()}</div>
                        <div class="time-col">
                            <div class="countdown">${ct}</div>
                            ${originalHtml}
                        </div>
                    </div>`;
            });
            section.innerHTML = rowsHtml;
            board.appendChild(section);
        });
    } catch (e) { console.error(e); }
}

loadCfg().then(() => {
    load();
    setInterval(load, cfg.refresh_delay * 1000);
    setInterval(tick, 1000);
});
</script>
</body>
</html>
"""

# --- Flask Routes ---
@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/config", methods=["GET", "POST"])
def handle_config():
    if request.method == "POST":
        cfg = load_config(); data = request.get_json()
        for key in ["stop_id", "stop_name", "max_per_quay"]:
            if key in data: cfg[key] = data[key]
        save_config(cfg); return jsonify(load_config())
    return jsonify(load_config())

@app.route('/fonts/<path:filename>')
def fonts(filename): return send_from_directory('fonts', filename)

@app.route("/data")
def data():
    cfg = load_config()
    query = f"""
    {{
      stopPlace(id: "{cfg['stop_id']}") {{
        estimatedCalls(numberOfDepartures: 50) {{
          aimedDepartureTime
          expectedDepartureTime
          quay {{ id }}
          destinationDisplay {{ frontText }}
          serviceJourney {{ line {{ publicCode }} }}
        }}
      }}
    }}
    """
    try:
        r = requests.post("https://api.entur.io/journey-planner/v3/graphql",
            headers={"ET-Client-Name": "raspi-board", "Content-Type": "application/json"},
            json={"query": query}, timeout=5)
        calls = r.json()["data"]["stopPlace"]["estimatedCalls"]
    except: return jsonify([])

    now = datetime.now(timezone.utc)
    grouped = {}
    for c in calls:
        expected = datetime.fromisoformat(c["expectedDepartureTime"].replace("Z", "+00:00"))
        if (expected - now).total_seconds() > MAX_MINUTES * 60: continue
        quay_id = c.get("quay", {}).get("id", "??").split(":")[-1]
        entries = grouped.setdefault(quay_id, [])
        if len(entries) < cfg["max_per_quay"]:
            entries.append({
                "line": c["serviceJourney"]["line"]["publicCode"],
                "dest": c["destinationDisplay"]["frontText"],
                "expectedDepartureTime": c["expectedDepartureTime"],
                "aimedDepartureTime": c["aimedDepartureTime"],
            })
    return jsonify([{"quay": q, "calls": v} for q, v in grouped.items()])

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False), daemon=True).start()
    webview.start(webview.create_window("Departure Board", "http://localhost:5000", width=720, height=1280, fullscreen=True, frameless=True, js_api=Api()))