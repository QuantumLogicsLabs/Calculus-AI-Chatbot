# CalcVoyager AI Chatbot - Communication Flow & Architecture

**Date**: July 19, 2026  
**Document Type**: Technical Architecture & Workflow  
**Audience**: DevOps Engineers, Backend Engineers, Frontend Developers  
**Status**: Complete

---

## Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [Service Components](#service-components)
3. [Communication Patterns](#communication-patterns)
4. [Request-Response Workflows](#request-response-workflows)
5. [Data Flow Diagrams](#data-flow-diagrams)
6. [Advanced Features](#advanced-features)
7. [Error Handling & Resilience](#error-handling--resilience)
8. [Performance Considerations](#performance-considerations)

---

## System Architecture Overview

The CalcVoyager chatbot is a **3-tier microservices architecture** with asynchronous communication:

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRONTEND (React Widget)                    │
│                    - Browser-based chat UI                       │
│                    - Embedded in web pages                       │
│                    - WebSocket/HTTP client                       │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP (REST + Server-Sent Events)
                       │ CORS-enabled
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              BACKEND SERVICE (Starlette)                         │
│              Port: 8002                                          │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ Routes:                                              │       │
│  │  • POST /api/chat (synchronous chat)                │       │
│  │  • POST /api/chat/stream (SSE streaming)            │       │
│  │  • GET/POST /api/chat/sessions (session mgmt)       │       │
│  │  • GET /api/chat/history/{session_id}               │       │
│  │  • POST /api/chat/feedback (CB-12 feedback)         │       │
│  ├──────────────────────────────────────────────────────┤       │
│  │ Database: SQLite (aiosqlite)                        │       │
│  │  • chat_sessions (user chat history)                │       │
│  │  • chat_messages (session conversations)            │       │
│  │  • message_feedback (CB-12 ratings)                 │       │
│  │  • topic_progress (CB-18 adaptive difficulty)       │       │
│  └──────────────────────────────────────────────────────┘       │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP (localhost:8001)
                       │ Internal network
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│          AI SERVICE (FastAPI)                                    │
│          Port: 8001                                              │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ Routes:                                              │       │
│  │  • POST /chat (LLM inference + follow-ups)          │       │
│  │  • POST /chat/stream (SSE streaming tokens)         │       │
│  │  • POST /summarize (session summarization)          │       │
│  │  • GET /health (health check)                       │       │
│  ├──────────────────────────────────────────────────────┤       │
│  │ LLM Backend:                                        │       │
│  │  • OpenAI API (primary, 12s timeout)                │       │
│  │  • Mock responses (fallback via circuit breaker)    │       │
│  │  • Response cache (5min TTL)                        │       │
│  │  • SymPy verifier (CB-16 answer validation)         │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Service Components

### Frontend (React Widget)

**Location**: `frontend/src/components/Chatbot/`  
**Technology**: React.js  
**Entry Point**: Embedded chat widget in web pages

**Responsibilities**:
- Display chat UI (messages, input field, suggestions)
- Collect user input
- Make HTTP requests to backend
- Handle streaming responses (Server-Sent Events)
- Manage local UI state
- Display follow-up suggestions
- Handle feedback (CB-12 like/dislike buttons)

**Communication Method**: HTTP REST + SSE (Server-Sent Events)

---

### Backend Service (Starlette)

**Location**: `backend/app/`  
**Technology**: Starlette ASGI framework  
**Port**: 8002  
**Database**: SQLite (async via aiosqlite)

**Key Files**:
- `main.py` - CORS middleware, app initialization
- `routes/chat.py` - All chat endpoint logic
- `database/db.py` - Database layer (SQLite)
- `auth/auth_utils.py` - User authentication

**Responsibilities**:
- Accept user messages from frontend
- Manage user sessions and conversation history
- Call aiService for LLM responses
- Store chat history in SQLite
- Track user feedback (CB-12)
- Compute adaptive difficulty (CB-18)
- Implement rate limiting (CB-11)
- Manage CORS for frontend access
- Perform session summarization (CB-13)

**Communication Method**: HTTP REST (upstream to aiService)

---

### AI Service (FastAPI)

**Location**: `aiService/`  
**Technology**: FastAPI + async Python  
**Port**: 8001  
**LLM**: OpenAI API

**Key Files**:
- `chatbot.py` - FastAPI app and route handlers
- `services/llm_client.py` - OpenAI integration + CB-20 resilience
- `services/math_verifier.py` - SymPy validation (CB-16)
- `services/.env` - Configuration (API keys, timeouts)

**Responsibilities**:
- Receive chat requests from backend
- Format prompts (system prompt + user message + context)
- Call OpenAI API with timeout handling
- Parse follow-up suggestions from response
- Stream tokens back to backend
- Implement circuit breaker (CB-20)
- Cache responses (CB-20)
- Validate mathematical answers (CB-16)
- Generate session summaries (CB-13)

**Communication Method**: HTTP REST + SSE (upstream from backend)

---

## Communication Patterns

### Pattern 1: Simple Request-Response (Synchronous Chat)

```
CLIENT → BACKEND → AI SERVICE → OPENAI → AI SERVICE → BACKEND → CLIENT

Timing: ~2-5 seconds
Best for: Simple queries, low-latency requirements
```

**Flow**:
```
1. Frontend sends POST /api/chat with user message
2. Backend validates authentication + rate limits
3. Backend retrieves active session or creates new one
4. Backend calls aiService POST /chat
5. aiService calls OpenAI with CB-20 timeout (12s)
6. OpenAI returns complete response
7. aiService parses follow-ups, returns to backend
8. Backend stores message in SQLite
9. Backend returns response + suggestions to frontend
10. Frontend displays message and follow-ups
```

**Latency Breakdown**:
- Frontend → Backend: ~50ms
- Backend processing: ~100ms
- Backend → aiService: ~50ms
- aiService → OpenAI: ~1500-3000ms (LLM inference)
- OpenAI → aiService: ~50ms
- aiService processing: ~100ms
- aiService → Backend: ~50ms
- Backend database write: ~100-200ms
- Backend → Frontend: ~50ms
- **Total**: 2-3.5 seconds (typical)

---

### Pattern 2: Streaming Response (Server-Sent Events)

```
CLIENT → BACKEND ┐
                 └→ AI SERVICE ┐
                               └→ OPENAI
                                  (stream tokens)
                               ┌→
                    ┌──────────┘
        ┌──────────┘
← ← ← ← ← (SSE frames, one per token)

Timing: Streaming starts in 1-2s, tokens arrive every 10-50ms
Best for: User experience (visible typing), long responses
```

**Flow**:
```
1. Frontend sends POST /api/chat/stream with user message
2. Backend sets up HTTP response with media_type="text/event-stream"
3. Backend starts generator function and returns StreamingResponse
4. Backend calls aiService POST /chat/stream
5. aiService sets up OpenAI streaming mode
6. OpenAI begins token stream (typically 1-2 tokens/100ms)
7. aiService receives tokens and yields SSE frames:
   data: {"delta": "token_text"}
8. Backend receives frames and re-yields to frontend
9. Frontend receives SSE events and appends tokens to UI in real-time
10. User sees typing effect as tokens arrive
11. Final event includes suggestions + metadata
12. Both services and frontend close streams
```

**SSE Event Format**:
```
event: message
data: {"delta": "The"}

event: message
data: {"delta": " derivative"}

event: message
data: {"delta": " of"}

...

event: done
data: {"suggestions": ["What about...", "Can you show..."], "done": true}

event: [DONE]
data: [DONE]
```

---

### Pattern 3: Resilience with Circuit Breaker (CB-20)

```
ATTEMPT 1 (Success):
Backend → aiService → OpenAI (12s timeout) → Response ✓

ATTEMPT 2-3 (Failures):
Backend → aiService → OpenAI (timeout/error) ✗
Backend → aiService → OpenAI (timeout/error) ✗

CIRCUIT OPENS (after 3 failures):
Backend → aiService → Mock Response (fallback) ✓
          (circuit breaker prevents OpenAI calls)

WAIT 60 SECONDS, CIRCUIT RESETS:
Backend → aiService → OpenAI (attempt recovery) ✓
```

**Configuration** (in `aiService/services/.env`):
```
PRIMARY_TIMEOUT_SECONDS=12        # timeout for OpenAI call
CIRCUIT_FAILURE_THRESHOLD=3       # failures before opening
CIRCUIT_RESET_SECONDS=60          # time until retry attempt
LLM_CACHE_TTL_SECONDS=300         # cache identical responses
```

---

## Request-Response Workflows

### Workflow 1: User Sends First Chat Message

```
Timeline: T0 → T+3s

T0:00    User types "What is a derivative?" and clicks Send
         └─→ Frontend prepares request payload:
             {
               "messages": [
                 {"role": "user", "content": "What is a derivative?"}
               ],
               "context": "Calculus",
               "topic_key": "derivatives",
               "page_url": "/learn/calc101"
             }

T0:05    Frontend POSTs to Backend:
         POST /api/chat
         Authorization: Bearer <token>
         └─→ Sent over CORS-enabled HTTP

T0:15    Backend receives request
         ├─→ Validates JWT token (auth/auth_utils.py)
         ├─→ Checks rate limits (CB-11)
         ├─→ Retrieves user_id from token
         ├─→ Queries SQLite for active session
         └─→ Creates new session if none exist

T0:25    Backend queries CB-18 adaptive difficulty:
         "user_123 studying derivatives -> current level = intermediate"
         └─→ Retrieves from topic_progress table

T0:35    Backend calls aiService:
         POST http://127.0.0.1:8001/chat
         {
           "message": "What is a derivative?",
           "topic": "Calculus",
           "difficulty": "intermediate",
           "history": [],
           "summary": ""
         }

T0:45    aiService receives request
         ├─→ Loads system prompt (Cal's personality)
         ├─→ Loads user message and context
         ├─→ Constructs OpenAI request with temperature=0.7
         └─→ Calls OpenAI API with timeout=12s

T0:50    OpenAI processes inference
         └─→ Generates calculus explanation with LaTeX math

T2:50    OpenAI returns complete response (2s inference time):
         "The derivative measures the rate of change...
          $$\frac{df}{dx}$$
          [FOLLOW_UPS]
          1. How do you compute derivatives using limits?
          2. What are partial derivatives?
          [/FOLLOW_UPS]"

T2:60    aiService parses response:
         ├─→ Extracts answer: "The derivative measures..."
         ├─→ Parses follow-ups: ["How do you compute...", "What are partial..."]
         └─→ Returns JSON to backend:
             {
               "answer": "The derivative measures...",
               "suggestions": ["How do you compute...", "What are partial..."]
             }

T2:75    Backend receives aiService response
         ├─→ Stores user message in chat_messages table
         ├─→ Stores assistant response in chat_messages table
         ├─→ Updates chat_sessions.updated_at timestamp
         ├─→ Calls record_topic_message() for CB-18 progress
         └─→ Returns to frontend:
             {
               "reply": "The derivative measures...",
               "suggestions": ["How do you compute...", "What are partial..."],
               "message_id": 42,
               "session_id": "uuid-123",
               "difficulty": "intermediate"
             }

T2:85    Frontend receives response
         ├─→ Displays assistant message in chat bubble
         ├─→ Renders follow-up buttons below message
         └─→ Ready for next user input

T3:00    User sees full response on screen
```

**Database State After**:
```sql
-- chat_sessions
INSERT INTO chat_sessions 
  (user_id, session_id, title, updated_at)
VALUES (123, 'uuid-abc', 'What is a derivative?', 1721414400)

-- chat_messages (user)
INSERT INTO chat_messages
  (user_id, session_id, message_type, content, metadata)
VALUES (123, 'uuid-abc', 'user', 'What is a derivative?', 
        '{"page_url": "/learn/calc101", "topic": "derivatives"}')

-- chat_messages (assistant)
INSERT INTO chat_messages
  (user_id, session_id, message_type, content, metadata)
VALUES (123, 'uuid-abc', 'assistant', 'The derivative measures...', 
        '{"page_url": "/learn/calc101", "topic": "derivatives", 
          "suggestions": ["How do you compute...", "What are partial..."]}')

-- topic_progress (CB-18)
UPDATE topic_progress 
SET message_count = 1, difficulty_score = 0, difficulty_level = 'intermediate'
WHERE user_id = 123 AND topic = 'derivatives'
```



---

### Workflow 2: User Rates a Message (CB-12 Feedback)

```
Timeline: T0 → T+0.5s

T0:00    User sees assistant response and clicks "👍 Helpful"
         └─→ Frontend identifies message_id=42 from previous response

T0:05    Frontend POSTs to Backend:
         POST /api/chat/feedback
         {
           "message_id": 42,
           "feedback": "like"
         }

T0:15    Backend receives feedback
         ├─→ Validates user owns this message
         ├─→ Calls upsert_feedback() in database
         └─→ Calls record_topic_feedback(user_id, topic, "like")

T0:25    Backend updates CB-18 adaptive difficulty:
         Current: difficulty_score = 0, level = 'intermediate'
         
         Apply feedback:
         └─→ LIKE_DELTA = +2.0
         └─→ New score = 0 + 2.0 = 2.0
         └─→ Still 'intermediate' (< 3.0 threshold)
         
         Update:
         UPDATE topic_progress 
         SET difficulty_score = 2.0, like_count = 1
         WHERE user_id = 123 AND topic = 'derivatives'

T0:35    Backend returns success:
         {
           "success": true,
           "updated_progress": {
             "topic": "derivatives",
             "difficulty_level": "intermediate",
             "difficulty_score": 2.0,
             "like_count": 1
           }
         }

T0:50    Frontend displays confirmation (subtle animation)
         └─→ Next message from this student will be "intermediate"
             (or moved up if multiple likes accumulate)
```

**CB-18 Difficulty Progression**:
```
Starting score: 0.0 (beginner level)

Per helpful message: +2.0
Per unhelpful message: -3.0 (penalty for bad fit)
Per 4 consecutive clean messages: +1.0 (mastery bonus)

Level Thresholds:
  Score ≥ 8.0  → advanced
  Score ≥ 3.0  → intermediate
  Score < 3.0  → beginner

Example Progression:
  T1: 1st message        score=0   → beginner
  T2: User rates helpful score=2.0 → intermediate (crosses 3.0 threshold after ~2 likes)
  T5: 4th message clean  score=3.0 → intermediate
  T6: User rates helpful score=5.0 → intermediate
  T7: User rates unhelpful score=2.0 → drops back
  T10: Consistent good   score=8.0+ → advanced
```

---

### Workflow 3: Streaming Response with Follow-ups

```
Timeline: T0 → T+3.5s (with visible token stream)

T0:00    User submits: "Compute d/dx[x²]"
         Frontend chooses streaming endpoint:
         POST /api/chat/stream

T0:50    Backend receives, same validation as Workflow 1
         └─→ Calls aiService POST /chat/stream

T0:60    aiService sets up OpenAI streaming
         └─→ Calls OpenAI with stream=True

T1:20    OpenAI returns first token
         └─→ "The"

T1:25    aiService yields SSE frame:
         data: {"delta": "The"}

T1:30    Frontend receives frame:
         ├─→ Parses JSON
         ├─→ Appends "The" to message bubble
         ├─→ Shows cursor (blinking caret)
         └─→ Update is immediate (~5ms paint)

T1:45    Next tokens arrive at ~50ms intervals:
         "derivative", "of", "x²", "with", "respect", "to", "x", "is", "2x"

T1:50    aiService finished generating:
         └─→ Parses follow-ups from complete response
         └─→ Yields final SSE frame:
             data: {"done": true, "suggestions": [...]}

T2:55    Frontend receives final frame
         ├─→ Removes cursor
         ├─→ Renders follow-up suggestion buttons
         ├─→ Message reads: "The derivative of x² with respect to x is 2x"
         └─→ User sees typed-out effect complete

T3:00    Full response visible + interactive
         (User sees ~2-3 seconds of typing effect)
```

**SSE Frame Stream Example**:
```
T0:00 POST /api/chat/stream

T1:25 event: message
      data: {"delta": "The"}

T1:35 event: message
      data: {"delta": " derivative"}

T1:45 event: message
      data: {"delta": " of"}

T1:55 event: message
      data: {"delta": " x"}

T2:05 event: message
      data: {"delta": "²"}

T2:15 event: message
      data: {"delta": " with"}

T2:25 event: message
      data: {"delta": " respect"}

T2:35 event: message
      data: {"delta": " to"}

T2:45 event: message
      data: {"delta": " x"}

T2:55 event: message
      data: {"delta": " is"}

T3:05 event: message
      data: {"delta": " 2x"}

T3:15 event: done
      data: {"done": true, "suggestions": 
             ["Why is the derivative 2x?", 
              "Show using the limit definition"]}

T3:20 Connection closes
```

---

### Workflow 4: Session Summarization (CB-13)

```
Timeline: Triggered after 10 messages in a session

T0:00    User submits their 10th message in session
         └─→ Backend stores message normally

T0:50    Backend checks: has session reached 10 messages?
         ├─→ Query: SELECT COUNT(*) FROM chat_messages 
         │           WHERE session_id = 'uuid-abc'
         └─→ Result: 10 (even number)

T0:60    Backend checks: was session summarized < 10 messages ago?
         ├─→ Query: SELECT summary_through_count FROM chat_sessions
         │           WHERE session_id = 'uuid-abc'
         └─→ Result: 0 (never summarized)
         └─→ Gap = 10 - 0 = 10, triggers summarization

T0:70    Backend fetches first N-10 messages (message 1-0 = none for first summary)
         └─→ Actually keeps last ~10 to prevent token bloat

T0:80    Backend calls aiService POST /summarize:
         {
           "messages": [
             {"role": "user", "content": "What is a derivative?"},
             {"role": "assistant", "content": "The derivative measures..."},
             ...
             {"role": "user", "content": "Compute d/dx[x²]"},
             {"role": "assistant", "content": "The derivative of x²..."}
           ],
           "previous_summary": ""
         }

T1:50    aiService calls OpenAI to generate summary
         └─→ Typical inference: ~1s

T2:60    aiService returns summary:
         {
           "summary": "Student is learning basic calculus derivatives. 
                      Grasped definition and simple power rule. 
                      Ready for chain rule next."
         }

T2:70    Backend stores summary:
         UPDATE chat_sessions 
         SET summary = 'Student is learning...', 
             summary_through_count = 10
         WHERE session_id = 'uuid-abc'

T2:80    On next message, if CB-13 context is used:
         ├─→ Backend retrieves summary from database
         ├─→ Passes to aiService: "summary": "Student is learning..."
         └─→ OpenAI uses context to continue appropriately
```

**Why Summarization Matters**:
```
Problem: Token limit on OpenAI context window
  Each message consumes tokens (~50-200 tokens per message)
  Storing 100+ messages = 5000+ tokens = expensive + slow

Solution: Summarize periodically
  ✓ Reduces token count (summary ~200 tokens vs 500+ for raw messages)
  ✓ Maintains context ("student is intermediate level on derivatives")
  ✓ Triggers every 10 new messages (N=10 configurable)
  ✓ Fallback: use raw history if summarization fails
```

---

## Data Flow Diagrams

### Flow A: Message Request → Database → Response

```
┌─────────────┐
│  Frontend   │
│  (React)    │
└──────┬──────┘
       │ POST /api/chat
       │ {message, context, topic_key, page_url}
       ▼
┌──────────────────────────────────────────────┐
│ Backend (Starlette)                          │
│                                              │
│ 1. Auth check (JWT token validation)         │
│ 2. Rate limit check (CB-11)                  │
│ 3. Fetch active session or create new        │
│ 4. Load CB-18 difficulty level for topic     │
│ 5. Load CB-13 session summary                │
│ 6. Call aiService → OpenAI → aiService       │
│ 7. Parse response + follow-ups               │
│                                              │
└──────┬───────────────────────────────────────┘
       │ 8. Store in SQLite (async)
       ▼
┌──────────────────────────────────────────────┐
│ SQLite Database (aiosqlite)                  │
│                                              │
│ INSERT chat_messages (user message)          │
│ INSERT chat_messages (assistant response)    │
│ UPDATE chat_sessions (updated_at)            │
│ UPDATE topic_progress (CB-18 scoring)        │
│ INSERT message_feedback (if rated - CB-12)   │
│ UPDATE chat_sessions (summary if triggered)  │
│                                              │
└──────────────────────────────────────────────┘
       │ 9. Query complete, return to backend
       ▼
┌──────────────────────────────────────────────┐
│ Backend (continued)                          │
│                                              │
│ 10. Return JSON response:                    │
│     {                                        │
│       "reply": "The derivative is...",       │
│       "suggestions": [...],                  │
│       "message_id": 42,                      │
│       "difficulty": "intermediate"           │
│     }                                        │
│                                              │
└──────┬───────────────────────────────────────┘
       │ HTTP 200 + JSON body
       ▼
┌─────────────┐
│  Frontend   │
│  Display    │
│  response   │
└─────────────┘
```

### Flow B: Streaming Response with SSE

```
┌─────────────┐
│  Frontend   │
│  (React)    │
│  EventSource│
│ .onmessage  │
└──────┬──────┘
       │ POST /api/chat/stream
       ▼
┌──────────────────────────────────────────────┐
│ Backend StreamingResponse                    │
│ Content-Type: text/event-stream              │
│ Cache-Control: no-cache                      │
│                                              │
│ async def event_generator():                 │
│   for token in aiService_stream(...):        │
│     yield f"data: {json_token}\n\n"          │
│                                              │
└──────┬───────────────────────────────────────┘
       │ First frame arrives ~1-2s after request
       │ Subsequent frames every ~50ms
       ▼
┌──────────────────────────────────────────────┐
│ Frontend EventSource listener                │
│                                              │
│ event.data = '{"delta": "The"}'              │
│ → JSON.parse                                 │
│ → Append token to message_text               │
│ → Update DOM (fast ~5ms paint)               │
│ → Show typing effect                         │
│                                              │
└─────────────┘
       ▲
       │ Stream continues
       │ Token by token
       │ Until [DONE]
```



---

## Advanced Features

### CB-20: Model Fallback & Response Caching

**Purpose**: Ensure service availability even if OpenAI API fails

**How it Works**:

```
REQUEST
  ↓
Check Cache: Is this exact message cached?
  ├─ YES → Return cached response (TTL=5min)
  │        (Saves ~2-3s latency + OpenAI credits)
  │
  └─ NO → Continue to fallback sequence

Fallback Sequence:
  ├─ Attempt 1: Primary LLM (OpenAI) with timeout=12s
  │   └─ Waits up to 12 seconds
  │   ├─ Success → Cache response, return
  │   └─ Timeout/Error → Count failure
  │
  ├─ Attempt 2: Primary LLM (OpenAI) with timeout=12s
  │   ├─ Success → Cache response, return
  │   └─ Timeout/Error → Count failure (2 total)
  │
  ├─ Attempt 3: Primary LLM (OpenAI) with timeout=12s
  │   ├─ Success → Cache response, return
  │   └─ Timeout/Error → Count failure (3 total, CIRCUIT OPENS)
  │
  └─ Circuit Breaker Active (60 seconds):
     ├─ Return mock response
     │  "I'm experiencing high load. Try again in a moment."
     ├─ Log failure
     ├─ Wait 60 seconds
     └─ Reset counter, retry on next request

RESPONSE
  ↓
Cache for 5 minutes (identical requests reuse)
```

**Configuration**:
```env
# aiService/services/.env
USE_MOCK=False                    # Enable/disable mock fallback
PRIMARY_TIMEOUT_SECONDS=12        # How long to wait for OpenAI
LLM_CACHE_TTL_SECONDS=300         # 5 minutes
CIRCUIT_FAILURE_THRESHOLD=3       # Failures before circuit opens
CIRCUIT_RESET_SECONDS=60          # Time until retry attempt
```

**Caching Mechanism**:
```python
# In llm_client.py
import hashlib

message_hash = hashlib.md5(
    f"{message}|{topic}|{difficulty}".encode()
).hexdigest()

cache_key = f"llm_response:{message_hash}"

# Check cache
cached = cache.get(cache_key)
if cached and not expired:
    return cached  # Instant response

# Cache miss: call OpenAI
response = await call_openai(...)
cache.set(cache_key, response, ttl=300)
return response
```

---

### CB-16: Mathematical Answer Verification (SymPy)

**Purpose**: Validate calculus answers using symbolic math engine

**How it Works**:

```
User's Answer (from message): "The derivative is 2x"
         ↓
SymPy Parser: Try to parse "2x" as symbolic expression
         ├─ Success → sym.sympify("2x")
         └─ Failure → Return error

If parsed successfully:
         ├─ Compare with expected answer (from LLM verification step)
         ├─ Use SymPy equality: sym.simplify(user_answer - expected) == 0
         ├─ If equal → ✓ CORRECT
         ├─ If different → ✗ INCORRECT
         └─ If can't determine → ? NEEDS REVIEW

Return result to frontend:
         {
           "is_correct": true,
           "verification_method": "sympy",
           "explanation": "2x is the correct form"
         }
```

**Example**:
```python
from sympy import symbols, sympify, simplify

x = symbols('x')

user_answer = "2*x"
expected_answer = "2*x"

parsed_user = sympify(user_answer)     # 2*x
parsed_expected = sympify(expected_answer)  # 2*x

difference = simplify(parsed_user - parsed_expected)  # 0

if difference == 0:
    print("✓ CORRECT")
```

---

### CB-18: Adaptive Difficulty Tracking

**Purpose**: Personalize problem difficulty based on student performance

**How it Works**:

```
Student answers question on topic "derivatives"
         ↓
Backend records: record_topic_message(user_id, topic)
         ├─ Increment message_count
         ├─ Every 4 messages without feedback: +1.0 to difficulty_score
         └─ Recompute difficulty_level from score

Student clicks "👍 Helpful" (CB-12 feedback)
         ↓
Backend records: record_topic_feedback(user_id, topic, "like")
         ├─ Increment like_count
         ├─ Add +2.0 to difficulty_score
         └─ Recompute difficulty_level

Difficulty Level Thresholds:
         Score ≥ 8.0  → "advanced"
         Score ≥ 3.0  → "intermediate"
         Score < 3.0  → "beginner"

Student clicks "👎 Unhelpful"
         ├─ Increment dislike_count
         ├─ Add -3.0 to difficulty_score (penalty)
         └─ Floor at 0.0 (never negative)

Next Request from Same Student (same topic):
         └─ Backend loads: SELECT difficulty_level FROM topic_progress
                          WHERE user_id = ? AND topic = ?
         └─ Pass to aiService: "difficulty": "advanced"
         └─ OpenAI uses in system prompt to tailor response
```

**Database Schema**:
```sql
CREATE TABLE topic_progress (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    difficulty_level TEXT DEFAULT 'beginner',  -- beginner|intermediate|advanced
    difficulty_score REAL DEFAULT 0.0,         -- numeric score
    message_count INTEGER DEFAULT 0,           -- total messages
    like_count INTEGER DEFAULT 0,              -- positive feedback
    dislike_count INTEGER DEFAULT 0,           -- negative feedback
    updated_at INTEGER DEFAULT now,
    UNIQUE(user_id, topic)
);
```

**Example Progression**:
```
Session 1:
  T1: Send message "What is limit?" → count=1, score=0.0 → beginner
  T2: "Helpful" → score=2.0 → intermediate
  T3: Send message (count=2) → still intermediate

Session 2:
  T4: Send message (count=3) → still intermediate
  T5: Send message (count=4) → score += 1.0 (mastery) → score=3.0 → intermediate
  T6: "Helpful" → score=5.0 → intermediate

Session 3:
  T7: Send message (count=5) → still 5.0 → intermediate
  T8: "Helpful" → score=7.0 → intermediate
  T9: Send message (count=6) → score=7.0 → intermediate
  T10: "Helpful" → score=9.0 → ADVANCED! 🎉
  
  Next message from student will have "difficulty": "advanced"
  OpenAI will give more complex explanations, harder problems, etc.
```

---

### CB-12: User Feedback & Ratings

**Purpose**: Collect explicit feedback to improve responses and track CB-18 difficulty

**How it Works**:

```
Assistant Response Displayed
         ├─ "👍 Helpful" button
         ├─ "👎 Unhelpful" button
         └─ Other feedback options (too simple, too hard, etc.)

User clicks "👍 Helpful"
         ↓
Frontend POSTs /api/chat/feedback:
         {
           "message_id": 42,
           "feedback": "like"
         }

Backend:
         ├─ Validates user owns message_id
         ├─ Stores in message_feedback table
         ├─ Calls record_topic_feedback() → updates CB-18 score
         └─ Returns updated_progress

Frontend:
         ├─ Shows confirmation animation
         ├─ Disables buttons (feedback already recorded)
         └─ Updates progress indicator (if visible)
```

**Feedback Types**:
```python
VALID_FEEDBACK = [
    "like",           # ✓ Helpful, at right level
    "dislike",        # ✗ Not helpful, unclear, wrong
    "too_easy",       # Too simple for current level
    "too_hard",       # Too complex for current level
    "off_topic",      # Not answering the question
    "needs_clarification"  # Needs follow-up
]

# Each type has different impact on CB-18 scoring
LIKE_DELTA = +2.0
DISLIKE_DELTA = -3.0
TOO_EASY → move to advanced
TOO_HARD → move to beginner
```

**Database**:
```sql
CREATE TABLE message_feedback (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    feedback TEXT NOT NULL,        -- type of feedback
    created_at INTEGER DEFAULT now,
    updated_at INTEGER DEFAULT now,
    UNIQUE(message_id, user_id)   -- One feedback per user per message
);
```

---

### CB-13: Session Summarization

**Purpose**: Compress long conversation histories while retaining context

**Trigger**: Every 10 new messages in a session

**How it Works**:

```
Session starts: message_count = 0

Messages 1-9: Normal flow, no summarization

Message 10: User sends 10th message
         ├─ Backend stores message
         ├─ Queries: count(*) = 10 (even number)
         ├─ Check: summary_through_count = 0 (never summarized)
         ├─ Gap: 10 - 0 = 10 messages → TRIGGERS SUMMARIZE
         └─ Calls aiService POST /summarize

aiService receives:
         {
           "messages": [message_1, ..., message_9],
           "previous_summary": ""  // First summary
         }

OpenAI generates summary:
         "Student is learning introductory calculus. 
          Understands basic derivatives but struggles with chain rule. 
          Prefers step-by-step explanations. 
          Ready to move to integration next."

Backend stores:
         UPDATE chat_sessions 
         SET summary = 'Student is learning...',
             summary_through_count = 10
         WHERE session_id = 'uuid-abc'

Messages 11-20: Normal flow with summary available

Message 20: Trigger again
         ├─ Calls aiService with previous_summary:
         {
           "messages": [message_11, ..., message_19],
           "previous_summary": "Student is learning..."  // From above
         }
         └─ OpenAI refines summary with new context

Benefit: Reduces token count from 500-1000 to ~200
         while preserving student profile info
```

---

## Error Handling & Resilience

### Error Scenarios & Responses

| Scenario | Trigger | Response | User Sees |
|----------|---------|----------|-----------|
| **OpenAI Timeout** | Request > 12s | CB-20 fallback mock | "I'm experiencing high load. Try again..." |
| **OpenAI API Error** | 503/429/401 | CB-20 circuit breaker | Mock response or retry message |
| **Network Error** | Connection failed | Retry with exponential backoff | Briefly frozen UI → "Try again" button |
| **Database Error** | SQLite locked | Retry transaction | Response still sent (fallback: no history) |
| **Rate Limit Exceeded** | CB-11 limit hit | 429 Too Many Requests | "You've reached your message limit" |
| **Auth Failed** | Invalid JWT | 401 Unauthorized | Login/redirect to auth page |
| **Malformed Request** | Bad JSON body | 400 Bad Request | Client error (dev console) |
| **Server Error** | Unhandled exception | 500 Internal Server Error | "Something went wrong, try again" |

### Rate Limiting (CB-11)

**Rules**:
```python
class RateLimiter:
    # Authenticated users
    user_daily_limit = 50      # 50 messages per day
    user_window = 86400        # 24 hours
    
    # Guest users
    guest_session_limit = 10   # 10 messages per session
    guest_window = 3600        # 1 hour
```

**Algorithm**:
```python
async def check_limit(user_id, request):
    now = time.time()
    
    if user_id:
        key = f"user_{user_id}"
        limit = 50
        window = 86400
    else:
        key = f"guest_{ip_address}"
        limit = 10
        window = 3600
    
    if key not in limits:
        limits[key] = (1, now + window)
        return None  # Allowed
    
    count, reset_time = limits[key]
    
    if now > reset_time:
        # Window expired
        limits[key] = (1, now + window)
        return None  # Allowed, reset
    
    if count >= limit:
        # Exceeded
        retry_after = int(reset_time - now)
        return {
            "status": 429,
            "detail": f"Rate limit exceeded",
            "retry_after": retry_after
        }
    
    # Within limit
    limits[key] = (count + 1, reset_time)
    return None  # Allowed
```

---

## Performance Considerations

### Latency Budget (Total E2E Time: ~2-3 seconds)

```
Component                    Typical    Best    Worst
─────────────────────────────────────────────────────
Frontend → Backend          50ms      10ms    200ms
Backend auth/validation     50ms      10ms    100ms
Backend session lookup      50ms      10ms    200ms
Backend → aiService         50ms      10ms    200ms
aiService → OpenAI          1500ms    500ms   12000ms ⚠️
OpenAI inference            1500ms    500ms   12000ms ⚠️
OpenAI → aiService          50ms      10ms    200ms
aiService processing        100ms     50ms    500ms
Backend database write       100ms     10ms    500ms
Backend → Frontend          50ms      10ms    200ms
─────────────────────────────────────────────────────
TOTAL                       3500ms    1140ms  26900ms

Typical: 3-4 seconds
Best case (cached): 50-100ms
Worst case (timeout): 12+ seconds → CB-20 fallback
```

### Streaming Improves UX

```
Synchronous Request:
  0-3000ms:  ⏳ Loading spinner
  3000ms+:   Display full response
  Result:    3-second blank screen

Streaming Request:
  0-1000ms:  First token arrives, typing starts
  1000-2000ms: Tokens streaming, user sees content appearing
  2000-3000ms: Final tokens, follow-ups appear
  Result:    Content visible by 1-2 seconds, feels faster!
```

### Database Query Optimization

```sql
-- Indexed queries (fast, <10ms)
SELECT * FROM chat_sessions 
WHERE user_id = ? AND is_active = 1
ORDER BY updated_at DESC LIMIT 1;
-- Index: idx_sessions_user

SELECT * FROM topic_progress 
WHERE user_id = ? AND topic = ?;
-- Index: idx_progress_user

-- Potential slow queries (need optimization)
SELECT COUNT(*) FROM chat_messages 
WHERE session_id = ?;
-- Add index: CREATE INDEX idx_messages_session ON chat_messages(session_id)

SELECT * FROM message_feedback 
WHERE message_id = ? AND user_id = ?;
-- Already has UNIQUE(message_id, user_id) constraint (acts as index)
```

### Caching Strategy

| Data | TTL | Location | Hit Rate |
|------|-----|----------|----------|
| LLM responses (CB-20) | 5min | In-memory | 10-20% (identical questions rare) |
| User session | 5min | SQLite | 100% (persistent) |
| Topic progress | 1min | Memory | 80% (reused in loop) |
| Summarization | Session | SQLite | 100% (persistent) |

---

## Deployment Architecture

### Development

```
Frontend: http://localhost:3000 (npm run dev)
Backend:  http://localhost:8002 (python -m uvicorn backend.app.main:app)
AI Service: http://localhost:8001 (python -m uvicorn aiService.chatbot:app)

All services on localhost → direct HTTP calls
No CORS needed (same origin)
```

### Staging/Production (Docker Compose)

```yaml
version: '3.8'
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8002:8002"
    environment:
      - DATABASE_URL=sqlite:///calcvoyager.db
    depends_on:
      - aiservice

  aiservice:
    build:
      context: .
      dockerfile: Dockerfile.aiservice
    ports:
      - "8001:8001"
    environment:
      - GROK_API_KEY=${GROK_API_KEY}
      - USE_MOCK=False
      - PRIMARY_TIMEOUT_SECONDS=12
      - LLM_CACHE_TTL_SECONDS=300

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_BACKEND_URL=http://backend:8002
```

### Production (Kubernetes)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: calcvoyager-backend
spec:
  selector:
    app: backend
  ports:
    - protocol: TCP
      port: 8002
      targetPort: 8002

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: calcvoyager-backend
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: backend
        image: calcvoyager/backend:latest
        ports:
        - containerPort: 8002
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
```

---

## Summary

The CalcVoyager chatbot uses a **3-tier microservices architecture** with:

1. **Frontend (React)** - User interface, HTTP + SSE client
2. **Backend (Starlette)** - Session management, auth, database, rate limiting
3. **AI Service (FastAPI)** - LLM integration, caching, circuit breaker

**Key Communication Patterns**:
- Synchronous REST for simple requests (~3-4s latency)
- Streaming SSE for better UX (~2-3s with visible typing)
- Async database operations for non-blocking I/O
- Circuit breaker + caching for resilience (CB-20)

**Advanced Features**:
- Adaptive difficulty (CB-18): Personalize based on feedback
- User feedback (CB-12): 👍 Helpful / 👎 Unhelpful ratings
- Session summarization (CB-13): Compress long histories
- Math verification (CB-16): SymPy validation of answers

All communication is fully asynchronous, resilient to failures, and optimized for end-user latency.
