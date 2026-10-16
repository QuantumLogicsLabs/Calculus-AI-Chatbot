# Run locally in VS Code (Windows PowerShell)

Open `C:\Calculus-AI-Chatbot` in VS Code. Dependencies are installed in `.venv`
and `frontend/node_modules` on this machine. Choose `.venv\Scripts\python.exe`
with **Python: Select Interpreter**.

Use three terminals. No virtual-environment activation is required.
For fresh setup, copy the three `.env.example` files as described in `README.md`.
The commands below explicitly select a local mock demo; terminal environment
variables take priority over `.env` values.

## Terminal 1: AI service (mock demo, no API key)

```powershell
cd C:\Calculus-AI-Chatbot
$env:USE_MOCK = "True"
.\.venv\Scripts\python.exe -m uvicorn aiService.chatbot:app --host 127.0.0.1 --port 8001
```

## Terminal 2: Backend

```powershell
cd C:\Calculus-AI-Chatbot
$env:AI_SERVICE_URL = "http://127.0.0.1:8001"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8002
```

## Terminal 3: Frontend

```powershell
cd C:\Calculus-AI-Chatbot\frontend
$env:REACT_APP_API_URL = "http://127.0.0.1:8002"
$env:BROWSER = "none"
npm.cmd start
```

Open http://localhost:3000 and click **Ask tutor**. Mock mode returns explicitly
labelled placeholder text; it tests the connection and UI, not calculus accuracy.
Stop each service with Ctrl+C in its terminal.

## Real tutor

Stop terminal 1. Create the ignored file `aiService/services/.env` locally with:

```dotenv
GROQ_API_KEY=your_actual_groq_key
USE_MOCK=False
```

Then restart terminal 1 with:

```powershell
cd C:\Calculus-AI-Chatbot
$env:USE_MOCK = "False"
.\.venv\Scripts\python.exe -m uvicorn aiService.chatbot:app --host 127.0.0.1 --port 8001
```

The code calls Groq using `openai/gpt-oss-120b`; a Grok/xAI key is not interchangeable.
Real-provider failures now surface explicit errors; demo replies require explicit
mock mode. Keep keys in the ignored `.env`, never in `.env.example`, Git or chat.
After restarting both services, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_live_chat --backend-url http://127.0.0.1:8002
```

The command consumes up to two model calls and saves evidence under `test-results/`.
Old already-running servers must be restarted to pick up Python code changes.

## Reinstall dependencies if needed

```powershell
cd C:\Calculus-AI-Chatbot
New-Item -ItemType Directory -Force .cache/tmp | Out-Null
$env:TEMP = "C:\Calculus-AI-Chatbot\.cache\tmp"
$env:TMP = $env:TEMP
& "$env:LOCALAPPDATA\Python\pythoncore-3.12-64\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r aiService/requirements.txt
cd frontend
npm.cmd install --legacy-peer-deps
```

The Python path above is the Python 3.12 installation found on this machine.
On another machine, use its installed Python 3.11 or 3.12 executable instead.

## Previous local smoke checks (13 October 2026)

- Frontend compiled successfully and loaded in the browser.
- Backend and AI health endpoints returned HTTP 200.
- JSON chat and SSE streaming returned mock answers successfully.
- A browser question produced a completed streamed response without captured
  console errors or warnings. Page changes updated the topic label.
- Empty chat input returned HTTP 400.
- Isolated database checks passed for session creation, streamed message
  persistence, history retrieval, feedback and Markdown export.
- The standalone SymPy verifier correctly checked the derivative of `x**3`.

## Confirmed limitations from those checks

- Real-model accuracy was not tested; no Groq key was supplied.
- Closing and reopening the widget clears the visible conversation.
- Authentication accepts arbitrary tokens as the same user, while the frontend
  always runs as a guest. This prevents normal access to authenticated features.
- Browser CORS preflight rejects PUT and DELETE, blocking cross-origin session
  renaming and deletion.
- Sending the same like twice increases the topic score twice (2 then 4).
- The old feedback suite failed during collection in these historical checks.
  Phase 2 now imports the actual backend and uses isolated temporary databases;
  run `.venv\Scripts\python.exe -m pytest -q` for the repaired offline suite.
- Saved-session history formatting, follow-up extraction and live math
  verification remain disconnected as described in the repository review.
