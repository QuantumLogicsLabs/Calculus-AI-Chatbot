# CalcVoyager - AI Calculus Tutor

React chat widget with a Starlette backend, a separate Starlette AI service,
and SQLite chat persistence. The AI client uses Groq's OpenAI-compatible API
with the `openai/gpt-oss-120b` model. Mock mode returns placeholder text.

## Stack and entry points

```text
React (react-scripts) -> Starlette backend -> Starlette AI service -> Groq
                              |
                            SQLite
```

- Frontend: `frontend/src/index.js` -> `App.js`; HTML: `frontend/public/index.html`.
- Backend: `backend.app.main:app` (port 8002).
- AI service: `aiService.chatbot:app` (port 8001).
- `npm start` and `npm run build` use Create React App / react-scripts.
  Vite and `VITE_API_URL` are not used by this repository.
- FastAPI is currently listed as a dependency, but both server apps use Starlette.
- The active database is `backend/app/database/calcvoyager.db`; Supabase is not integrated.

## Local setup (Windows PowerShell)

Use Python 3.11 or 3.12 and Node.js with npm. Run from the repository root.
If `python` points to a Windows Store alias, use the installed Python executable;
see `LOCAL_RUN.md` for the path verified on the current workstation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r aiService/requirements.txt
npm.cmd --prefix frontend install --legacy-peer-deps

# Copy templates only when the local files do not already exist.
if (-not (Test-Path aiService/services/.env)) { Copy-Item aiService/services/.env.example aiService/services/.env }
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
if (-not (Test-Path frontend/.env)) { Copy-Item frontend/.env.example frontend/.env }
```

The examples start in mock mode and contain no credentials. Keep actual `.env`
files untracked. Never place Groq keys in frontend configuration or chat messages.

Start three terminals from the repository root:

```powershell
# Terminal 1: AI service; reads aiService/services/.env automatically
.\.venv\Scripts\python.exe -m uvicorn aiService.chatbot:app --host 127.0.0.1 --port 8001
```

```powershell
# Terminal 2: backend; explicitly loads backend/.env
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --env-file backend/.env --host 127.0.0.1 --port 8002
```

```powershell
# Terminal 3: frontend; react-scripts automatically reads frontend/.env
$env:BROWSER = "none"
npm.cmd --prefix frontend start
```

Open http://localhost:3000 and click **Ask tutor**. Stop services with Ctrl+C.
On Linux/macOS, use `.venv/bin/python` and `npm` in place of the Windows commands.

## Configuration

| File | Setting | Purpose |
| --- | --- | --- |
| `aiService/services/.env` | `USE_MOCK` | Defaults to `False` (real mode). Only explicit `True` enables demo replies. |
| `aiService/services/.env` | `GROQ_API_KEY` | Server-only Groq key; `GROK_API_KEY` is not interchangeable. |
| `aiService/services/.env` | `GROQ_MODEL` | Model ID; defaults to `openai/gpt-oss-120b`. |
| `aiService/services/.env` | `PRIMARY_TIMEOUT_SECONDS`, `STREAM_TOTAL_TIMEOUT_SECONDS`, `LLM_CACHE_TTL_SECONDS`, `CIRCUIT_*` | Provider/stream deadlines, cache and circuit breaker; see template. |
| `backend/.env` | `AI_SERVICE_URL` | AI service base URL, e.g. `http://127.0.0.1:8001`. |
| `backend/.env` | `ALLOWED_ORIGINS_EXTRA` | Extra frontend origins, comma-separated, without trailing slashes. |
| `frontend/.env` | `REACT_APP_API_URL` | Backend base URL, without trailing slash; defaults to localhost. |
| `frontend/.env` | `REACT_APP_CHAT_URL` | Optional direct AI-service base URL; leave empty for integrated mode. |

For real-model testing, set `USE_MOCK=False` and your Groq key in the AI `.env`,
then restart the AI service. Environment variables already set in the terminal
have priority over `.env` values. Frontend values are embedded at start/build time:
restart development or rebuild after changing them. A production frontend must
use a reachable backend URL, not localhost. In separate containers, the backend
must also use the reachable AI-service URL. No deployment is performed by setup.

## Available APIs

Backend routes include `/api/chat/` (JSON), `/api/chat/stream` (SSE), sessions,
history, feedback, topic progress and Markdown study-sheet export. The AI service
exposes `/chat`, `/chat/stream`, `/summarize` and `/health`.

## Current limitations and follow-up phases

- Only explicitly enabled mock mode returns demo text. Real-provider failures
  return JSON 503/504 or an SSE error frame, never a mock answer. Empty, truncated
  and failed streams are not cached or persisted as completed turns.
- Health checks report process health and mode, not successful provider access.
  Use the live verification command and response-source logs for provider evidence.
- Authentication is a placeholder: arbitrary Bearer tokens map to user 1, and the
  demo frontend always runs as a guest. Do not treat it as production authentication.
- Closing the widget clears its visible conversation. Saved-session UI mapping
  and follow-up extraction also need integration work.
- SymPy verification exists as a standalone utility; live chat does not invoke it.
- Auto-summary generation runs on the non-streaming path; the UI prefers streaming.
- Session rename/delete browser requests are blocked by the current CORS methods.
- SQLite requires durable storage for saved chats. In-memory cache, circuit breaker
  and rate limits are process-local and reset on restart.

## Tests and CI

Run `.venv\Scripts\python.exe -m pytest -q` for offline route, persistence,
context, cache, validator and streaming checks. Tests force mock mode, block the
provider path and isolate SQLite data; no API key or running server is needed.

GitHub Actions runs offline tests on Python 3.11/3.12 and a frontend production
build. Real response-quality/latency evaluation runs separately on the nightly
schedule or explicit selection and requires the `GROQ_API_KEY` repository secret.
Failures return nonzero rather than being suppressed. Fresh reports go to the
ignored `test-results/` directory. Existing SnapDeploy redeploy is manual-only;
pushes do not automatically change the old deployment.

See `aiService/tests/README_TESTING.md` for exact commands, coverage and limitations.

## Live verification

After adding a real Groq key to the ignored AI `.env` and restarting the services,
run `.venv\Scripts\python.exe -m scripts.verify_live_chat --backend-url http://127.0.0.1:8002`.
It asks two different questions, requires fresh `primary` / `live` answers, and
independently checks boxed results. Reports are saved in `test-results/live-smoke.json`.
The command rejects demo, cached, empty and unverifiable answers. It consumes up
to two model calls; it does not deploy anything. Source/mode metadata is also
returned by JSON responses and final SSE events. Logs include
`LLM_RESPONSE_SOURCE: served_by=primary mode=live` after successful model calls.
Cache and mock replies have distinct source labels.

See `LOCAL_RUN.md` for the workstation-specific run guide.

## License

Proprietary - Quantum Logics

## Free Render preview

See [RENDER_DEPLOY.md](RENDER_DEPLOY.md) for the single-service Docker deployment,
required private environment settings, preview limits and verification steps.
