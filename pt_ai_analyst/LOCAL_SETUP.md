# LOCAL_SETUP — running PomoTech AI Analyst fully offline

Same module, no cloud. The LLM runs on your machine (Ollama) and, optionally, the
Arabic voice is synthesized by a local speech server. No Gemini/Google keys, no
per-request quota, and your data never leaves your server.

Two independent pieces:
- **A. Local LLM** (required for analysis) — via the OpenAI-compatible transport.
- **B. Local voice / TTS** (optional) — for spoken Arabic replies offline.

---

## A. Local LLM (Ollama)

### 1. Install Ollama and pull a tool-capable model
The assistant works by **function/tool calling**, so the model **must support
tools** over the OpenAI-compatible API. Best open choices:

- **Qwen 2.5 Instruct** — excellent tool calling + good Arabic (recommended).
- **Llama 3.1 / 3.3 Instruct** — solid tool calling.
- ⚠️ **Gemma** — older versions do **not** expose function calling; only use a
  Gemma build that explicitly supports tools, otherwise queries won't run.

```bash
# install ollama (see ollama.com), then:
ollama pull qwen2.5:14b        # or qwen2.5:7b on a smaller GPU
ollama serve                    # exposes an OpenAI API at http://localhost:11434/v1
```

Pick the size your GPU/RAM can handle: 7B is light, 14B is a good balance, 32B/70B
are better at multi-step tool use if you have the hardware.

### 2. Point the module at it
**AI Analyst → Configuration → Providers → Default Provider**:

- **Provider** = `OpenAI-compatible (Chat Completions)`
- **Model** = `qwen2.5:14b` (match what you pulled)
- **API Base URL** = `http://localhost:11434/v1/chat/completions`
- **API Key** = anything (e.g. `ollama`) — the field is required but the local
  server ignores it.
- **Max Tool Rounds** = 4–6 (local models sometimes need a round or two more).
- Save.

### 3. Docker networking (important)
If Odoo runs in Docker (your logs show it does), `localhost` inside the container
is **not** your host. Use one of:

- `http://host.docker.internal:11434/v1/chat/completions` (Docker Desktop / recent
  Docker; on Linux add `--add-host=host.docker.internal:host-gateway` to the Odoo
  container), or
- your host's LAN IP, e.g. `http://192.168.1.50:11434/v1/chat/completions`, and
  start Ollama with `OLLAMA_HOST=0.0.0.0 ollama serve` so it accepts non-local
  connections.

Test from **inside** the Odoo container:
```bash
curl http://host.docker.internal:11434/v1/models
```

### 4. Try it
Open **AI Analyst → Assistant** and ask a question. If tool calls don't happen
(the model just chats without querying), switch to a more tool-reliable model
(Qwen 2.5 / Llama 3.1) — that's the usual cause.

---

## B. Local voice (optional, fully offline Arabic)

Browser voices don't cover Arabic on Linux, so for offline speech run a small
**OpenAI-compatible speech server** and point the module at it.

### Option 1 — openedai-speech (Piper voices, OpenAI `/v1/audio/speech`)
Run the server (Docker), which serves `/v1/audio/speech` and can use Piper voices
(including Arabic). Then in **Configuration → Avatar → Voice**:

- **Voice** = `Server / cloud voice`
- **Provider** = `OpenAI-compatible (local: Piper / Kokoro / openedai-speech)`
- **TTS Base URL** = `http://host.docker.internal:8000/v1`
- **TTS Model** = the model your server expects (e.g. `tts-1`)
- **Arabic Voice** / **English Voice** = the voice names your server exposes
  (e.g. a Piper `ar` voice for Arabic)
- **TTS API Key** = leave empty (local servers usually don't check it)
- Save.

The module sends the reply text to `/v1/audio/speech`, gets back MP3, and the page
plays it with the avatar lip-syncing — all offline.

### Option 2 — espeak-ng (quickest, robotic)
```bash
sudo apt update && sudo apt install -y speech-dispatcher espeak-ng
```
Leave **Voice = Browser voices** and use **Firefox**; it will have a (robotic)
Arabic voice via espeak. Good enough to validate the flow with zero setup.

### Speech input (talking to it)
Voice **input** (speech-to-text) uses the browser and needs Chrome/Edge over
HTTPS (or localhost) with microphone permission. This part uses the browser
regardless of the LLM/TTS being local. If you need fully-offline STT too, that's a
larger addition (a local Whisper server) — ask and I can wire it.

---

## C. What's cloud vs local now

| Piece | Cloud option | Local option |
|-------|-------------|--------------|
| Analysis (LLM) | Gemini / OpenAI | **Ollama + Qwen/Llama** (this guide) |
| Voice out (TTS) | Google Cloud TTS | **Piper/Kokoro via /v1/audio/speech**, or espeak |
| Voice in (STT) | — | Browser (Chrome/Edge); Whisper server possible |
| Data | leaves the server | **stays on your server** |

With A (and optionally B) configured, nothing about a query leaves your machine.

---

## D. Quick checklist

1. `ollama serve` reachable from the Odoo container (`/v1/models` responds).
2. Provider set to OpenAI-compatible + local URL + a tool-capable model.
3. Ask a question → it queries your data and answers.
4. (Optional) local speech server running → Avatar → Voice = server + local base URL.
5. Ask in Arabic → hear the reply offline.
