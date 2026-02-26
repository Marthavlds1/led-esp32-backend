"""
LED Controller — Backend Flask (solo API)
─────────────────────────────────────────
NO sirve archivos estáticos. Solo expone la API con CORS abierto.
El front corre por separado (Live Server, http.server, Netlify, etc.)

Endpoints:
  GET  /api/state   → La ESP32 física hace polling aquí cada 500 ms
  POST /api/state   → El front envía el nuevo color/count
  GET  /api/health  → Health check
"""

from __future__ import annotations
import json
import os
import re
import tempfile
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

# ─── Rutas ────────────────────────────────────────────────────────────────────
APP_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(APP_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LED_MIN, LED_MAX = 0, 8

# ─── App ──────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# CORS abierto: el front puede estar en cualquier origen
# (Live Server, file://, Netlify, GitHub Pages, etc.)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="state_", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def default_state() -> dict:
    return {"color": "#ff0000", "count": 0, "rev": 1, "updated_at": now_iso()}


def load_state() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        st = default_state()
        atomic_write(STATE_FILE, json.dumps(st))
        return st
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        st.setdefault("color", "#ff0000")
        st.setdefault("count", 0)
        st.setdefault("rev", 1)
        st.setdefault("updated_at", now_iso())
        return st
    except Exception:
        st = default_state()
        atomic_write(STATE_FILE, json.dumps(st))
        return st


def validate_state(color: str, count) -> tuple[bool, str]:
    if not isinstance(color, str) or not HEX_COLOR_RE.match(color):
        return False, "color inválido — usa formato #RRGGBB"
    try:
        count = int(count)
    except Exception:
        return False, "count debe ser un número entero"
    if not (LED_MIN <= count <= LED_MAX):
        return False, f"count inválido — debe estar entre {LED_MIN} y {LED_MAX}"
    return True, ""


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/state")
def get_state():
    """
    Usado por:
      - La ESP32 física (polling cada 500 ms)
      - El front al cargar la página (GET inicial)
    """
    return jsonify(load_state())


@app.post("/api/state")
def set_state():
    """
    Usado por el front cuando el usuario mueve sliders o presiona botones.
    Body JSON esperado: { "color": "#RRGGBB", "count": 0-8 }
    """
    payload = request.get_json(silent=True) or {}
    color = payload.get("color")
    count = payload.get("count")

    ok, msg = validate_state(color, count)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400

    st = load_state()
    st["color"]      = color
    st["count"]      = int(count)
    st["rev"]        = int(st.get("rev", 1)) + 1
    st["updated_at"] = now_iso()

    atomic_write(STATE_FILE, json.dumps(st))
    return jsonify({"ok": True, **st})


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": now_iso()})


# ─── Arranque ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"\n🟢  API corriendo en      http://0.0.0.0:{port}")
    print(f"📡  ESP32 apunta a        http://<TU_IP>:{port}/api/state")
    print(f"🌐  Front llama a         http://<TU_IP>:{port}/api/state\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
