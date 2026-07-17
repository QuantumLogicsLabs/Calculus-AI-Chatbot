# CalcVoyager — AI Calculus Tutor

Full-stack adaptive learning platform for multivariable calculus with AI tutoring, session persistence, feedback, and difficulty scaling.

## Quick Start

**Prerequisites:** Python 3.11+, Node.js 18+, xAI Grok API key

**Setup:**
```bash
# Backend
pip install -r aiService/requirements.txt backend/requirements.txt
mkdir -p aiService/services
echo "GROK_API_KEY=your_key_here\nUSE_MOCK=False" > aiService/services/.env

# Frontend
cd frontend && npm install
```

**Run (3 terminals):**
```bash
# Terminal 1: AI Service (port 8001)
cd aiService && python -m uvicorn chatbot:app --host 127.0.0.1 --port 8001

# Terminal 2: Backend (port 8002)
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

# Terminal 3: Frontend (port 3000)
cd frontend && npm start
```

Visit `http://localhost:3000`

## Architecture

```
React Frontend → Starlette Backend → FastAPI AI Service → Grok LLM
                        ↓
                    SQLite DB
```

## Features

- **Real-time Streaming Chat** - SSE-based token-by-token responses
- **Session Persistence** - Auto-summarization every 10 messages
- **Message Feedback** - Like/dislike persisted for auth users
- **Adaptive Difficulty** - Per-topic level tracking (beginner/intermediate/advanced)
- **Rate Limiting** - 50/day for auth users, 10/session for guests (HTTP 429)
- **Symbolic Math Verification** - SymPy validation for derivatives, integrals, limits
- **Scope Enforcement** - Cal refuses off-topic questions
- **Circuit Breaker & Caching** - Fallback to mock on LLM failures; 5-min response cache
- **Study Sheet Export** - Download sessions as Markdown with key formulas

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat` | POST | Main chat (returns `reply`, `message_id`, `session_id`, `difficulty`) |
| `/api/chat/feedback` | POST | Submit like/dislike feedback |
| `/api/chat/progress/{topic}` | GET | Get topic difficulty level |
| `/api/chat/sessions` | POST/GET | Create/list sessions |
| `/api/chat/sessions/{id}` | PUT/DELETE | Update/delete session |
| `/api/chat/history/{id}` | GET | Fetch session messages |
| `/api/chat/sessions/{id}/export` | GET | Download as Markdown |

## Configuration

**AI Service (.env):**
```
GROK_API_KEY=xai_...           # xAI API key
USE_MOCK=False                  # True for testing without API
CIRCUIT_FAILURE_THRESHOLD=3     # Failures before circuit opens
CIRCUIT_RESET_SECONDS=60        # Time before retry
PRIMARY_TIMEOUT_SECONDS=12      # LLM timeout
LLM_CACHE_TTL_SECONDS=300       # Cache 5 min
```

**Frontend (.env):**
```
REACT_APP_API_URL=http://127.0.0.1:8002
```

## Testing

```bash
# Mock mode (no API calls)
USE_MOCK=True python -m aiService.tests.chatbot_tests

# CB-12 Feedback tests
pytest aiService/tests/test_cb12_feedback.py -v

# GitHub Actions runs:
# - PR: mock tests on Python 3.11, 3.12
# - Nightly: real API tests with Grok key
# - Thresholds: CB-8 ≥10/10 scope, CB-9 ≥16/20 correctness
```

## Known Issues

- **Mock LLM**: Returns plaintext, no LaTeX/follow-ups (expected; real API has full formatting)
- **Windows Console**: Removed Unicode math symbols from test output for cp1252 compatibility
- **Session Summary**: Only triggers at ≥10 messages; guests never summarize (no persisted session)

## Dependencies

- Python: `starlette`, `fastapi`, `aiosqlite`, `sympy`, `openai`
- Frontend: `react`, `katex`

See `aiService/requirements.txt` and `backend/requirements.txt` for full lists.

## License

Proprietary — Quantum Logics
