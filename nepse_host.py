#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
nepse_host.py — Native Messaging bridge for NEPSE CAGR Extension
Mirrors the pattern from Toolbox's toolbox_host.py
"""

import sys, json, struct, subprocess, time, urllib.request, urllib.error, os

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
SERVER_PY   = os.path.join(SCRIPT_DIR, "nepse_cagr_server.py")
LOG_FILE    = os.path.join(SCRIPT_DIR, "nepse_engine.log")
VENV_PYTHON = os.path.join(SCRIPT_DIR, ".venv", "bin", "python3")

PORT_START     = 5758
PORT_END       = 5768
STARTUP_WAIT_S = 40
POLL_INTERVAL  = 0.5


# ── Native Messaging I/O ──────────────────────────────────────────────────────
def read_message():
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    msg_len = struct.unpack("<I", raw_len)[0]
    return json.loads(sys.stdin.buffer.read(msg_len).decode("utf-8"))

def send_message(msg):
    enc = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(enc)) + enc)
    sys.stdout.buffer.flush()


# ── Engine Control ────────────────────────────────────────────────────────────
def find_port():
    for p in range(PORT_START, PORT_END + 1):
        try:
            urllib.request.urlopen(f"http://localhost:{p}/ping", timeout=0.5)
            return p
        except:
            continue
    return None

def start_engine():
    python_bin = VENV_PYTHON if os.path.exists(VENV_PYTHON) else "/Users/karmagurung/.pyenv/shims/python3"
    with open(LOG_FILE, "a") as log:
        log.write(f"\n--- Engine start requested at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log.write(f"Using python: {python_bin}\n")
        log.write(f"Script: {SERVER_PY}\n")
    subprocess.Popen(
        [python_bin, SERVER_PY],
        cwd=SCRIPT_DIR,
        stdout=open(LOG_FILE, "a"),
        stderr=open(LOG_FILE, "a"),
        start_new_session=True
    )

def ensure_engine_running():
    port = find_port()
    if port:
        return port
    start_engine()
    deadline = time.time() + STARTUP_WAIT_S
    while time.time() < deadline:
        port = find_port()
        if port:
            return port
        time.sleep(POLL_INTERVAL)
    return None

def post_to_engine(port, path, payload):
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        f"http://localhost:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"Engine HTTP error {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    msg = read_message()
    if msg is None:
        send_message({"error": "No message received."})
        return

    action = msg.get("action", "")

    if action == "ping":
        port = find_port()
        send_message({"status": "running" if port else "stopped", "port": port})

    elif action == "cagr":
        payload = msg.get("payload", {})
        if not payload.get("symbol"):
            send_message({"error": "No symbol provided."})
            return
        port = ensure_engine_running()
        if not port:
            send_message({"error": f"Engine failed to start within {STARTUP_WAIT_S}s. Check {LOG_FILE}."})
            return
        result = post_to_engine(port, "/cagr", payload)
        send_message(result)

    else:
        send_message({"error": f"Unknown action: '{action}'"})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        send_message({"error": f"CRASH: {e} | {traceback.format_exc()}"})
