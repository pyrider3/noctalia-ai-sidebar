#!/usr/bin/env python3
"""
AI Sidebar Core Engine for Noctalia and Niri.
Supports Custom OpenAI-compatible API, Local Ollama, agy (Antigravity CLI), and Codex CLI.
Handles streaming, session persistence, selection grabbing, and screenshot capture.
"""

import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import base64
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATE_HOME = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
DATA_DIR = os.path.join(STATE_HOME, "noctalia", "plugins", "data", "pyrider3", "ai-sidebar")
os.makedirs(DATA_DIR, exist_ok=True)

SESSION_FILE = os.path.join(DATA_DIR, "session.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
PID_FILE = os.path.join(DATA_DIR, "generator.pid")
SCREENSHOT_FILE = os.path.join(DATA_DIR, "screenshot.png")

DEFAULT_CONFIG = {
    "backend": "api",  # "api", "ollama", "agy", "codex"
    "api_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "api_model": "deepseek-chat",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3.2",
    "system_prompt": "You are a helpful, concise AI coding assistant in a Linux desktop environment."
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(cfg)
            return merged
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def load_session():
    if not os.path.exists(SESSION_FILE):
        return {
            "messages": [],
            "status": "idle",
            "active_backend": "api",
            "error": "",
            "attached_image": ""
        }
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "messages": [],
            "status": "idle",
            "active_backend": "api",
            "error": "",
            "attached_image": ""
        }

def save_session(session):
    temp_file = SESSION_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, SESSION_FILE)

def write_pid(pid):
    with open(PID_FILE, "w") as f:
        f.write(str(pid))

def stop_current():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
    session = load_session()
    session["status"] = "idle"
    save_session(session)

# ----------------- Tool Helpers -----------------

def capture_selection():
    """Grab highlighted primary selection; fallback to standard clipboard."""
    text = ""
    try:
        res = subprocess.run(["wl-paste", "-p", "--no-newline"], capture_output=True, text=True, timeout=1.5)
        if res.returncode == 0 and res.stdout.strip():
            text = res.stdout.strip()
    except Exception:
        pass
    if not text:
        try:
            res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0 and res.stdout.strip():
                text = res.stdout.strip()
        except Exception:
            pass
    return text

def capture_screenshot():
    """Capture region with slurp and grim."""
    try:
        region = subprocess.run(["slurp"], capture_output=True, text=True, timeout=15)
        if region.returncode != 0 or not region.stdout.strip():
            return ""
        coords = region.stdout.strip()
        target = SCREENSHOT_FILE
        subprocess.run(["grim", "-g", coords, target], check=True, timeout=5)
        if os.path.exists(target):
            return target
    except Exception as e:
        sys.stderr.write(f"Screenshot error: {e}\n")
    return ""

def list_ollama_models(ollama_url="http://127.0.0.1:11434"):
    """Query local Ollama instance for installed models."""
    try:
        url = ollama_url.rstrip("/") + "/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "Noctalia-AISidebar"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return models
    except Exception:
        # Fallback to CLI ollama list if server is reachable locally
        try:
            res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                lines = res.stdout.strip().splitlines()[1:]
                models = [line.split()[0] for line in lines if line.strip()]
                return models
        except Exception:
            pass
    return []

# ----------------- Generation Logic -----------------

def run_api_stream(cfg, messages, image_path, session):
    url = cfg.get("api_url", "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions"
    api_key = cfg.get("api_key", "").strip()
    model = cfg.get("api_model", "deepseek-chat")
    sys_prompt = cfg.get("system_prompt", "")

    req_messages = []
    if sys_prompt:
        req_messages.append({"role": "system", "content": sys_prompt})

    for m in messages[:-1]:
        req_messages.append({"role": m["role"], "content": m["content"]})

    last_user_msg = messages[-1]["content"]
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as img_f:
                b64 = base64.b64encode(img_f.read()).decode("utf-8")
            req_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": last_user_msg},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            })
        except Exception:
            req_messages.append({"role": "user", "content": last_user_msg})
    else:
        req_messages.append({"role": "user", "content": last_user_msg})

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}" if api_key else ""
    }
    body = {
        "model": model,
        "messages": req_messages,
        "stream": True
    }

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")

    content_acc = ""
    reasoning_acc = ""
    last_flush = time.time()

    with urllib.request.urlopen(req, timeout=60) as resp:
        for line in resp:
            line = line.decode("utf-8").strip()
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                delta = chunk["choices"][0].get("delta", {})
                if "reasoning_content" in delta and delta["reasoning_content"]:
                    reasoning_acc += delta["reasoning_content"]
                if "content" in delta and delta["content"]:
                    content_acc += delta["content"]

                if time.time() - last_flush > 0.08:
                    session["messages"][-1]["content"] = content_acc
                    session["messages"][-1]["thinking"] = reasoning_acc
                    save_session(session)
                    last_flush = time.time()
            except Exception:
                continue

    session["messages"][-1]["content"] = content_acc
    session["messages"][-1]["thinking"] = reasoning_acc
    session["status"] = "idle"
    save_session(session)

def run_ollama_stream(cfg, messages, image_path, session):
    url = cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    model = cfg.get("ollama_model", "llama3.2")
    sys_prompt = cfg.get("system_prompt", "")

    req_messages = []
    if sys_prompt:
        req_messages.append({"role": "system", "content": sys_prompt})

    for m in messages[:-1]:
        req_messages.append({"role": m["role"], "content": m["content"]})

    last_user_msg = messages[-1]["content"]
    last_dict = {"role": "user", "content": last_user_msg}
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as img_f:
                b64 = base64.b64encode(img_f.read()).decode("utf-8")
            last_dict["images"] = [b64]
        except Exception:
            pass
    req_messages.append(last_dict)

    body = {
        "model": model,
        "messages": req_messages,
        "stream": True
    }

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")

    content_acc = ""
    thinking_acc = ""
    in_think_tag = False
    last_flush = time.time()

    with urllib.request.urlopen(req, timeout=90) as resp:
        for line in resp:
            line = line.decode("utf-8").strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
                delta = chunk.get("message", {}).get("content", "")
                if "<think>" in delta:
                    in_think_tag = True
                    delta = delta.replace("<think>", "")
                if "</think>" in delta:
                    parts = delta.split("</think>")
                    thinking_acc += parts[0]
                    content_acc += parts[1]
                    in_think_tag = False
                elif in_think_tag:
                    thinking_acc += delta
                else:
                    content_acc += delta

                if time.time() - last_flush > 0.08:
                    session["messages"][-1]["content"] = content_acc
                    session["messages"][-1]["thinking"] = thinking_acc
                    save_session(session)
                    last_flush = time.time()
            except Exception:
                continue

    session["messages"][-1]["content"] = content_acc
    session["messages"][-1]["thinking"] = thinking_acc
    session["status"] = "idle"
    save_session(session)

def run_agy_cli(cfg, messages, session):
    prompt = messages[-1]["content"]
    cmd = ["agy", "-p", prompt]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    write_pid(proc.pid)

    content_acc = ""
    last_flush = time.time()

    for line in proc.stdout:
        content_acc += line
        if time.time() - last_flush > 0.1:
            session["messages"][-1]["content"] = content_acc
            save_session(session)
            last_flush = time.time()

    proc.wait()
    session["messages"][-1]["content"] = content_acc.strip()
    session["status"] = "idle"
    save_session(session)

def run_codex_cli(cfg, messages, image_path, session):
    prompt = messages[-1]["content"]
    cmd = ["codex", "exec", "--skip-git-repo-check"]
    if image_path and os.path.exists(image_path):
        cmd.extend(["-i", image_path])
    cmd.append(prompt)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    write_pid(proc.pid)

    raw_output = ""
    content_acc = ""
    recording = False
    last_flush = time.time()

    for line in proc.stdout:
        raw_output += line
        if line.strip() == "codex":
            recording = True
            continue
        elif recording and line.strip().startswith("tokens used"):
            recording = False
            continue
        elif recording:
            content_acc += line
            if time.time() - last_flush > 0.1:
                session["messages"][-1]["content"] = content_acc
                save_session(session)
                last_flush = time.time()

    proc.wait()
    # In case format differed, fallback to trimmed raw output
    if not content_acc.strip() and raw_output.strip():
        content_acc = raw_output.strip()

    session["messages"][-1]["content"] = content_acc.strip()
    session["status"] = "idle"
    save_session(session)

def generate_worker(backend, prompt, image_path):
    write_pid(os.getpid())
    cfg = load_config()
    session = load_session()

    # User message
    session["messages"].append({
        "role": "user",
        "content": prompt,
        "image": image_path,
        "time": time.strftime("%H:%M")
    })

    # Assistant placeholder
    session["messages"].append({
        "role": "assistant",
        "content": "",
        "thinking": "",
        "backend": backend,
        "time": time.strftime("%H:%M")
    })
    session["status"] = "streaming"
    session["error"] = ""
    session["attached_image"] = ""
    save_session(session)

    try:
        if backend == "api":
            run_api_stream(cfg, session["messages"][:-1], image_path, session)
        elif backend == "ollama":
            run_ollama_stream(cfg, session["messages"][:-1], image_path, session)
        elif backend == "agy":
            run_agy_cli(cfg, session["messages"][:-1], session)
        elif backend == "codex":
            run_codex_cli(cfg, session["messages"][:-1], image_path, session)
        else:
            raise ValueError(f"Unknown backend: {backend}")
    except Exception as e:
        session = load_session()
        session["status"] = "idle"
        session["error"] = str(e)
        if session["messages"] and session["messages"][-1]["role"] == "assistant" and not session["messages"][-1]["content"]:
            session["messages"][-1]["content"] = f"⚠️ 请求出错: {e}"
        save_session(session)
    finally:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

# ----------------- CLI Dispatch -----------------

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "get-session"

    if action == "get-session":
        session = load_session()
        print(json.dumps(session, ensure_ascii=False))

    elif action == "get-config":
        cfg = load_config()
        print(json.dumps(cfg, ensure_ascii=False))

    elif action == "save-config":
        if len(sys.argv) > 2:
            new_cfg = json.loads(sys.argv[2])
            save_config(new_cfg)
            print("ok")

    elif action == "new-chat":
        session = {
            "messages": [],
            "status": "idle",
            "active_backend": load_config().get("backend", "api"),
            "error": "",
            "attached_image": ""
        }
        save_session(session)
        print("ok")

    elif action == "stop":
        stop_current()
        print("stopped")

    elif action == "capture-selection":
        text = capture_selection()
        print(text)

    elif action == "capture-screen":
        img = capture_screenshot()
        print(img)

    elif action == "list-ollama-models":
        models = list_ollama_models()
        print(json.dumps(models, ensure_ascii=False))

    elif action == "send":
        backend = sys.argv[2] if len(sys.argv) > 2 else "api"
        prompt = sys.argv[3] if len(sys.argv) > 3 else ""
        image_path = sys.argv[4] if len(sys.argv) > 4 else ""

        # Fork worker so CLI returns immediately to Noctalia Luau
        pid = os.fork()
        if pid == 0:
            # Child process
            os.setsid()
            generate_worker(backend, prompt, image_path)
            sys.exit(0)
        else:
            print(f"started {pid}")
