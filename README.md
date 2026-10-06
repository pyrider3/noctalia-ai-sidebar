# AI Sidebar

A full-height AI assistant sidebar and in-place context copilot for Noctalia shell and Niri. Query custom OpenAI-compatible APIs (DeepSeek, Moonshot, SiliconFlow), local Ollama models, Antigravity CLI (agy), and Codex CLI with streaming responses, screen selection capture, and multimodal screenshot attachments.

## Plugin

| Field | Value |
| --- | --- |
| ID | `pyrider3/ai-sidebar` |
| Entries | Bar widget: `ai-sidebar-widget`; panel: `ai-sidebar-panel` |

## Requirements

Install `python3`, `wl-copy`, and `wl-paste` on `PATH`. `grim` and `slurp` are optional but recommended for interactive screenshot questions.

## Usage

Add the `ai-sidebar-widget` to your bar in Settings → Bar. Click the bar icon to toggle the full-height right sidebar, or toggle it directly via IPC:

```sh
noctalia msg panel-toggle pyrider3/ai-sidebar:ai-sidebar-panel
```

### Shortcuts and Keybindings

- **Global Toggle**: Bind `Mod+S` in `niri` to summon or dismiss the sidebar without moving your hands away from the keyboard.
- **In-Panel Shortcuts**: Press `Enter` to send your prompt, or `Shift+Enter` to insert a newline. Press `Escape` to close the panel.
- **Screen Selection**: Click "Grab Selection" to instantly paste highlighted text from any Wayland window (`wl-paste -p`).
- **Screenshot Ingestion**: Click "Screenshot" to select a region on screen with `slurp` and query vision-capable models.

## Settings

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| `default_backend` | `select` | `agy` | Default engine backend when opening the sidebar (`agy`, `codex`, `api`, `ollama`). |
| `api_url` | `string` | `https://api.deepseek.com/v1` | Base URL for OpenAI-compatible completions endpoint. |
| `api_key` | `string` | `""` | Bearer authorization key for API provider. |
| `api_model` | `string` | `deepseek-chat` | Model name sent in API payload. |
| `ollama_url` | `string` | `http://127.0.0.1:11434` | Local Ollama HTTP service endpoint. |
| `ollama_model` | `string` | `llama3.2` | Local model tag to query on Ollama. |
| `system_prompt` | `string` | `You are a helpful, concise AI coding assistant in a Linux desktop environment.` | System prompt preamble injected into queries. |

## Notes

- Session conversation history and settings cache are stored in `$XDG_STATE_HOME/noctalia/plugins/data/pyrider3/ai-sidebar/`.
- No remote code is downloaded or executed; CLI backends invoke your locally installed `agy`, `codex`, or `ollama` binaries.
