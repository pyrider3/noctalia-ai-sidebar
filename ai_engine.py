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
    "backend": "agy",  # "api", "ollama", "agy", "codex"
    "api_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "api_model": "deepseek-chat",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3.2",
    "system_prompt": (
        "你是运行在 Linux (Arch Linux + Noctalia + Niri) 桌面环境中的全能 AI 助理与电脑操控管家。"
        "你具备直接操控用户电脑、打开程序、调节系统设置、切换壁纸和执行命令的真实能力。\n"
        "当用户需要你操控电脑或进行简单工作时：\n"
        "1. 用亲切简明的中文说明你的操作。\n"
        "2. 在回答中使用 ```desktop-action\\n{...}\\n``` 格式输出执行指令（系统会自动捕获并执行）。\n"
        "支持的操作类型：\n"
        "- 打开应用: {\"action\": \"open_app\", \"target\": \"kitty|firefox|wechat|nautilus|steam|io.missioncenter.MissionCenter\"}\n"
        "- 调节音量: {\"action\": \"volume\", \"value\": \"up\"|\"down\"|\"mute\"|50}\n"
        "- 调节亮度: {\"action\": \"brightness\", \"value\": \"up\"|\"down\"}\n"
        "- 切换壁纸: {\"action\": \"wallpaper\", \"value\": \"next\"|\"random\"}\n"
        "- 切换主题: {\"action\": \"theme\", \"value\": \"dark\"|\"light\"|\"toggle\"}\n"
        "- 打开设置: {\"action\": \"settings\"}\n"
        "- 执行命令: {\"action\": \"exec\", \"command\": \"<具体bash指令>\"}\n"
    )
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

# ----------------- Desktop Actions & System Controller -----------------

APP_ALIASES = {
    "终端": "kitty",
    "terminal": "kitty",
    "kitty": "kitty",
    "微信": "wechat",
    "wechat": "wechat",
    "浏览器": "firefox",
    "firefox": "firefox",
    "火狐": "firefox",
    "edge": "microsoft-edge-stable",
    "chrome": "google-chrome-stable",
    "文件管理器": "nautilus",
    "文件夹": "nautilus",
    "nautilus": "nautilus",
    "任务管理器": "io.missioncenter.MissionCenter",
    "资源监视器": "io.missioncenter.MissionCenter",
    "missioncenter": "io.missioncenter.MissionCenter",
    "音乐": "kitty -e kew",
    "kew": "kitty -e kew",
    "播放器": "celluloid",
    "steam": "steam",
    "设置": "noctalia msg settings-open",
    "系统设置": "noctalia msg settings-open",
    "控制中心": "noctalia msg settings-open",
    "壁纸引擎": "w-engine",
    "计算器": "gnome-calculator",
}

def execute_desktop_action(action_type, target="", value=""):
    """
    Directly execute desktop actions on Arch Linux / Noctalia / Niri.
    Returns (success: bool, message: str)
    """
    try:
        action_type = str(action_type).strip().lower()
        if action_type == "open_app":
            app_cmd = APP_ALIASES.get(str(target).strip().lower(), str(target).strip())
            subprocess.Popen(app_cmd, shell=True, start_new_session=True)
            return True, f"已为你启动应用: {target}"

        elif action_type == "volume":
            val = str(value).strip().lower()
            if val in ["up", "大", "+", "加"]:
                subprocess.run(["noctalia", "msg", "volume-up"], check=True)
                return True, "已调大系统音量 🔊"
            elif val in ["down", "小", "-", "减"]:
                subprocess.run(["noctalia", "msg", "volume-down"], check=True)
                return True, "已调小系统音量 🔉"
            elif val in ["mute", "静音"]:
                subprocess.run(["noctalia", "msg", "volume-mute"], check=True)
                return True, "已切换静音状态 🔇"
            elif val.isdigit():
                subprocess.run(["noctalia", "msg", "volume-set", val], check=True)
                return True, f"已将音量调整为 {val}% 🔊"
            else:
                subprocess.run(["noctalia", "msg", "volume-up"], check=True)
                return True, "已调整音量 🔊"

        elif action_type == "brightness":
            val = str(value).strip().lower()
            if val in ["up", "亮", "+", "加"]:
                subprocess.run(["noctalia", "msg", "brightness-up"], check=True)
                return True, "已调高屏幕亮度 ☀️"
            elif val in ["down", "暗", "-", "减"]:
                subprocess.run(["noctalia", "msg", "brightness-down"], check=True)
                return True, "已调低屏幕亮度 🌙"
            else:
                subprocess.run(["noctalia", "msg", "brightness-up"], check=True)
                return True, "已调整屏幕亮度"

        elif action_type == "wallpaper":
            val = str(value).strip().lower()
            if val in ["random", "随机"]:
                subprocess.run(["noctalia", "msg", "wallpaper-random"], check=True)
                return True, "已随机切换一张桌面壁纸 🖼️"
            else:
                subprocess.run(["noctalia", "msg", "wallpaper-next"], check=True)
                return True, "已切换下一张桌面壁纸 🖼️"

        elif action_type == "theme":
            val = str(value).strip().lower()
            if val in ["dark", "深色", "暗色", "黑夜"]:
                subprocess.run(["noctalia", "msg", "theme-mode-set", "dark"], check=True)
                return True, "已切换至深色模式 🌙"
            elif val in ["light", "浅色", "亮色", "白天"]:
                subprocess.run(["noctalia", "msg", "theme-mode-set", "light"], check=True)
                return True, "已切换至浅色模式 ☀️"
            else:
                subprocess.run(["noctalia", "msg", "theme-mode-toggle"], check=True)
                return True, "已切换桌面明暗主题 🌓"

        elif action_type == "settings":
            subprocess.run(["noctalia", "msg", "settings-open"], check=True)
            return True, "已打开桌面控制中心与设置 ⚙️"

        elif action_type == "workspace":
            ws = str(value).strip()
            subprocess.run(["niri", "msg", "action", "focus-workspace", ws], check=True)
            return True, f"已切换至工作区 {ws} 🖥️"

        elif action_type == "exec":
            cmd = str(target or value).strip()
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            out = res.stdout.strip() or res.stderr.strip()
            if not out:
                out = "命令已成功执行（无返回输出）"
            return True, f"执行指令 `{cmd}` 完成:\n```\n{out}\n```"

        else:
            return False, f"未知的操作指令: {action_type}"
    except Exception as e:
        return False, f"执行操作失败: {e}"

def try_fast_desktop_intent(prompt):
    p = prompt.strip().lower()

    # 1. 屏幕亮度调节 (支持 "帮我把亮度弄低点", "亮度调高", "暗一点", "亮一点", "太暗了", "太亮了" 等)
    if any(k in p for k in ["亮度", "屏幕"]) or any(k in p for k in ["暗一点", "暗点", "暗些", "亮一点", "亮点", "亮些", "太暗", "太亮"]):
        if any(w in p for w in ["低", "暗", "降", "小", "减", "弱", "调低", "太亮"]):
            ok, msg = execute_desktop_action("brightness", value="down")
            return f"{msg}"
        elif any(w in p for w in ["高", "亮", "提", "大", "加", "增", "强", "调高", "太暗"]):
            ok, msg = execute_desktop_action("brightness", value="up")
            return f"{msg}"

    # 2. 音量与声音控制 (支持 "帮我把音量弄大点", "大点声", "小点声", "把声音调小", "静音" 等)
    if any(w in p for w in ["静音", "闭麦", "别出声", "消音"]):
        ok, msg = execute_desktop_action("volume", value="mute")
        return f"{msg}"
    if any(k in p for k in ["音量", "声音", "声"]):
        if any(w in p for w in ["大", "高", "提", "加", "升", "响"]):
            ok, msg = execute_desktop_action("volume", value="up")
            return f"{msg}"
        elif any(w in p for w in ["小", "低", "降", "减"]):
            ok, msg = execute_desktop_action("volume", value="down")
            return f"{msg}"
    if any(k in p for k in ["大点声", "大声点", "放大声音"]):
        ok, msg = execute_desktop_action("volume", value="up")
        return f"{msg}"
    if any(k in p for k in ["小点声", "小声点", "放小声音", "太吵了"]):
        ok, msg = execute_desktop_action("volume", value="down")
        return f"{msg}"

    # 3. 切换壁纸 (支持 "换张壁纸", "切壁纸", "随机壁纸", "换个背景" 等)
    if "壁纸" in p or "背景" in p:
        if any(w in p for w in ["随机", "随便"]):
            ok, msg = execute_desktop_action("wallpaper", value="random")
            return f"{msg}"
        elif any(w in p for w in ["换", "切", "下", "变", "新"]):
            ok, msg = execute_desktop_action("wallpaper", value="next")
            return f"{msg}"

    # 4. 主题明暗模式
    if any(w in p for w in ["深色模式", "暗色模式", "黑夜模式", "夜间模式", "暗黑模式"]):
        ok, msg = execute_desktop_action("theme", value="dark")
        return f"{msg}"
    if any(w in p for w in ["浅色模式", "明亮模式", "白天模式", "日间模式", "白色模式"]):
        ok, msg = execute_desktop_action("theme", value="light")
        return f"{msg}"
    if "主题" in p and any(w in p for w in ["换", "切", "变"]):
        ok, msg = execute_desktop_action("theme", value="toggle")
        return f"{msg}"

    # 5. 常见应用程序启动 (支持 "帮我打开微信", "启动火狐", "把终端打开", "开一下文件管理器" 等)
    app_targets = [
        (["终端", "kitty", "terminal", "命令行"], "kitty", "终端 (Kitty)"),
        (["微信", "wechat"], "wechat", "微信"),
        (["火狐", "firefox", "浏览器", "网页"], "firefox", "Firefox 浏览器"),
        (["文件管理器", "文件夹", "资源管理器", "nautilus"], "nautilus", "文件管理器 (Nautilus)"),
        (["任务管理器", "资源监视器", "系统监视器", "missioncenter", "mission center"], "io.missioncenter.MissionCenter", "任务管理器 (Mission Center)"),
        (["音乐", "听歌", "kew", "播放器"], "kitty -e kew", "终端音乐播放器 Kew"),
        (["设置", "控制中心", "系统设置", "桌面设置"], "noctalia msg settings-open", "桌面控制中心与设置"),
        (["steam", "蒸汽平台"], "steam", "Steam 客户端"),
        (["计算器"], "gnome-calculator", "计算器"),
    ]
    is_open_intent = any(w in p for w in ["打开", "启动", "运行", "开启", "开一下", "唤起", "帮我开", "进", "帮我打开"])
    for keywords, app_id, name in app_targets:
        if any(kw in p for kw in keywords):
            if is_open_intent or len(p) <= 8:
                ok, msg = execute_desktop_action("open_app", app_id)
                return f"🚀 **已为你启动应用: {name}**\n\n如有其他系统操作或指令需求，随时告诉我！"

    # 6. 关闭窗口
    if any(k in p for k in ["关掉窗口", "关闭窗口", "关闭当前窗口", "关掉当前窗口", "把窗口关了", "关掉这个窗口", "关闭当前应用"]):
        execute_desktop_action("exec", target="niri msg action close-window")
        return "已为你关闭当前窗口 ✕"

    # 7. 屏幕区域截屏
    if any(k in p for k in ["截个图", "截屏", "截图", "区域截屏"]):
        execute_desktop_action("exec", target="noctalia msg screenshot-region")
        return "已启动屏幕区域截屏 📸"

    # 8. 打开设置/控制中心
    if any(k in p for k in ["打开设置", "打开控制中心", "进入设置", "系统设置"]):
        ok, msg = execute_desktop_action("settings")
        return f"{msg}"

    # 9. 清空通知
    if any(k in p for k in ["清空通知", "清理通知", "清除通知"]):
        execute_desktop_action("exec", target="noctalia msg notification-clear-active")
        return "已清空屏幕活跃通知 🧹"

    return None

def process_embedded_actions(text):
    """
    Scans for ```desktop-action\n{...}\n``` blocks in LLM response and executes them.
    Appends execution outcomes to the text.
    """
    import re
    pattern = r"```desktop-action\s*(\{.*?\})\s*```"
    matches = re.findall(pattern, text, re.DOTALL)
    if not matches:
        return text

    results = []
    for match in matches:
        try:
            data = json.loads(match)
            act = data.get("action", "")
            target = data.get("target", data.get("command", ""))
            val = data.get("value", "")
            ok, msg = execute_desktop_action(act, target=target, value=val)
            results.append(msg)
        except Exception as e:
            results.append(f"解析系统指令失败: {e}")

    if results:
        text += "\n\n---\n" + "\n\n".join([f"> ⚡ **系统操作反馈**: {r}" for r in results])
    return text

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
    cmd = ["agy", "--dangerously-skip-permissions", "-p", prompt]
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
    cmd = ["codex", "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]
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

    # 1. 优先尝试快捷桌面系统操作（毫秒级响应）
    fast_reply = try_fast_desktop_intent(prompt)
    if fast_reply:
        session["messages"].append({
            "role": "assistant",
            "content": fast_reply,
            "thinking": "",
            "backend": backend,
            "time": time.strftime("%H:%M")
        })
        session["status"] = "idle"
        session["error"] = ""
        session["attached_image"] = ""
        save_session(session)
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
        return

    # 2. 正常流式大模型推理
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

        # 检查大模型回答中是否包含 ```desktop-action 执行块
        session = load_session()
        if session["messages"] and session["messages"][-1]["role"] == "assistant":
            raw_c = session["messages"][-1]["content"]
            processed_c = process_embedded_actions(raw_c)
            if processed_c != raw_c:
                session["messages"][-1]["content"] = processed_c
                save_session(session)

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

    elif action == "action-exec":
        act_type = sys.argv[2] if len(sys.argv) > 2 else ""
        target = sys.argv[3] if len(sys.argv) > 3 else ""
        val = sys.argv[4] if len(sys.argv) > 4 else ""
        ok, msg = execute_desktop_action(act_type, target=target, value=val)
        print(json.dumps({"success": ok, "message": msg}, ensure_ascii=False))
