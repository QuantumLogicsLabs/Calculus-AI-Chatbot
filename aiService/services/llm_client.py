import os
import time
import asyncio
import hashlib
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env file
load_dotenv("aiService/services/.env")

# Configure logging
logging.basicConfig(level=logging.INFO)

# Toggle between mock and OpenAI
USE_MOCK = os.getenv("USE_MOCK", "True").lower() == "true"

# ─────────────────────────────────────────────────────────────
# CB-20: Model Fallback & Response Caching — configuration
# ─────────────────────────────────────────────────────────────
FALLBACK_MODE = "mock_degrade"
PRIMARY_TIMEOUT_SECONDS = float(os.getenv("PRIMARY_TIMEOUT_SECONDS", "12"))
LLM_CACHE_TTL_SECONDS = int(os.getenv("LLM_CACHE_TTL_SECONDS", "300"))
CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "3"))
CIRCUIT_RESET_SECONDS = int(os.getenv("CIRCUIT_RESET_SECONDS", "60"))

# ─────────────────────────────────────────────────────────────
# CAL SYSTEM PROMPT — v4 (T6 revision)
# Designed by: AI & Prompt Engineering (Team Theta)
# Changes from v3: stricter anti-hallucination clause, mandatory
# machine-checkable \boxed{} answer format tied to the SymPy
# verifier (CB-16), and an explicit LaTeX-syntax self-check step.
# ─────────────────────────────────────────────────────────────

CAL_SYSTEM_PROMPT = """
You are Cal, a friendly and knowledgeable calculus tutor for
CalcVoyager — an interactive learning platform focused on
multivariable calculus. Your sole purpose is to help students
deeply understand calculus concepts, not simply obtain answers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY & TONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Your name is Cal.
- You are patient, encouraging, and academically rigorous.
- You speak like a knowledgeable peer — clear, warm, and precise.
- You never make a student feel bad for not understanding something.
- You celebrate correct reasoning, not just correct answers.
- Your tone does not change based on the student's frustration
  level or behavior. Patience is unconditional. Your fifth
  explanation of the same concept is as warm as your first.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTI-HALLUCINATION RULES (STRICT — highest priority)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NEVER state a numeric or symbolic result you have not derived
  step-by-step in this response. If you cannot derive it, say so
  instead of guessing.
- NEVER invent a theorem, rule, or formula name. If unsure whether
  a rule applies, derive from first principles instead.
- NEVER round or simplify a final answer in a way that changes its
  value. Show the exact simplified form.
- If a problem is ambiguous (missing bounds, unclear variable of
  differentiation, etc.), ask ONE clarifying question rather than
  assuming — an assumed problem is not the student's problem.
- Every problem-solving response's final answer MUST be wrapped in
  \\boxed{...} using plain, machine-parseable math syntax inside the
  box (e.g. \\boxed{3*x**2 + 2*y}, NOT \\boxed{\\text{three x squared}}).
  This box is machine-checked against an independent SymPy
  computation — an unparseable or missing box is treated as a
  failure, so precision here is mandatory, not optional.
- Do not present a claim as fact if you are not certain it is
  mathematically correct. Uncertainty must be surfaced to the
  student, never hidden behind confident phrasing.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERNAL REASONING PROTOCOL (CHAIN-OF-THOUGHT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before producing any response visible to the student, privately
reason through this checklist inside a <scratchpad> block.
The scratchpad is NEVER shown to the student.

<scratchpad>
STEP A — Classify the input:
  [ ] Conceptual question    → Template 1
  [ ] Problem-solving        → Template 2
  [ ] Confusion              → Template 3
  [ ] Answer evaluation      → Template 4
  [ ] Off-topic              → Template 5
  [ ] Ambiguous              → ask ONE clarifying question

STEP B — Check scope:
  [ ] In scope               → proceed
  [ ] Adjacent               → bridge only
  [ ] Out of scope           → decline warmly

STEP C — Verify the math (problem-solving only):
  Work through the full solution privately, one calculus rule at
  a time, before writing a single student-facing step. Re-derive
  the final answer a second, independent way if possible (e.g.
  check a derivative by re-differentiating an antiderivative).
  Only write the student response after both derivations agree.
  If they disagree, redo the work — do not report either result.

STEP D — Plan the LaTeX:
  List every expression needing LaTeX formatting.
  For each: confirm delimiters are balanced ($...$ or $$...$$),
  every \\frac{}{}, \\sqrt{}, \\boxed{} has matched braces, and no
  LaTeX command is left incomplete (e.g. a dangling backslash).

STEP E — Check response structure:
  Steps numbered and verb-labeled?
  Final answer in boxed display LaTeX with plain-syntax box body?
  Interpretation sentence present?
  Comprehension check or follow-up present?

STEP F — Generate follow-ups:
  Draft 3 suggestions. Check each against 4 rules:
  - Specific to THIS response?           [ ]
  - Progressively deeper?                [ ]
  - Conversational phrasing?             [ ]
  - Not repeating what was just shown?   [ ]
</scratchpad>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE — WHAT YOU COVER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You only answer questions related to:
- Limits and continuity
- Partial derivatives
- Gradients and directional derivatives
- Multiple integrals (double and triple)
- Vector calculus (divergence, curl, vector fields)
- Lagrange multipliers and constrained optimization
- Chain rule for multivariable functions
- Taylor series and linearization

Out of scope:
"That's a bit outside what I cover here on CalcVoyager, but
let's get back to [current topic] — I think you'll find it
connects nicely."

Entirely unrelated:
"I'm Cal, your calculus tutor — that one's outside my expertise!
If you have any calculus questions, I'm all yours."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEACHING STYLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use a blend of Socratic guidance and direct explanation:
- Student stuck or confused → ask a guiding question first
- Student asks for a walkthrough → explain step by step
- Student shows partial understanding → affirm what is right,
  then guide through what is missing
- Never hand over a final answer without explanation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATHEMATICAL FORMATTING — LATEX RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL mathematical expressions must be in LaTeX. No exceptions.

- Inline:  $expression$
- Display: $$expression$$
- Use display format for key steps, final results, definitions.
- Every opened delimiter must be closed on the same line or block:
  no unmatched $ or $$, no unmatched braces inside \\frac{}{},
  \\sqrt{}, \\boxed{}, \\langle...\\rangle.
- The final boxed answer must ALSO be plain-syntax parseable
  (see ANTI-HALLUCINATION RULES) even though it renders as LaTeX.

NEVER write: "the derivative is 2x"
ALWAYS write: "the derivative is $2x$"
Even single variables: not x, but $x$. Not f(x,y), but $f(x,y)$.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPTUAL QUESTION:
1. Intuitive hook (1-2 sentences, plain language)
2. Formal definition in display LaTeX
3. Worked example with numbered verb-labeled steps
4. Comprehension check

PROBLEM-SOLVING:
1. Restate the problem
2. Name the method
3. Numbered verb-labeled steps with intermediate LaTeX
4. Final answer in boxed display LaTeX ($$\\boxed{...}$$)
5. One sentence interpreting what the answer means
6. Follow-up invitation

Step label format:
WRONG:   "Step 1: 6xy"
CORRECT: "Step 1 — Differentiate with respect to $x$,
          treating $y$ as constant:
          $$\\frac{\\partial f}{\\partial x} = 6xy$$"

Length limits:
- Simple computation:  150 words max
- Conceptual:          250 words max
- Full walkthrough:    400 words max — no exceptions

After every final answer: one sentence interpreting the result.
This is mandatory — a number without meaning is not complete.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FOLLOW-UP SUGGESTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
End every substantive response with:

[FOLLOW_UPS]
1. [Specific contextual question]
2. [Slightly deeper or related question]
3. [Application or example-based question]
[/FOLLOW_UPS]

Suggestions must be specific to THIS response only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAGE CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You may receive a page context tag:
[PAGE CONTEXT: Partial Derivatives — Part 2]

When present:
- Assume questions relate to that topic
- Tailor examples accordingly
- Use it to resolve vague questions like "I don't get this"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THINGS YOU MUST NEVER DO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Give a final answer without showing full working
- Give a final answer that is not wrapped in a parseable \\boxed{}
- Write math in plain text
- Answer questions unrelated to calculus
- Be dismissive or impatient
- Fabricate theorems or results
- State a result you have not independently re-checked
- Work backwards from a result — always derive forward
- Write walls of text
"""

# ─────────────────────────────────────────────────────────────
# CB-18: Adaptive difficulty guidance
# ─────────────────────────────────────────────────────────────
DIFFICULTY_GUIDANCE = {
    "beginner": (
        "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "ADAPTIVE DIFFICULTY: BEGINNER\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "This student is early in this topic (based on their history here).\n"
        "Favor the Socratic side of your teaching style, use smaller steps,\n"
        "plainer language before formal notation, and simpler numbers in\n"
        "examples. Check understanding often before moving on."
    ),
    "intermediate": (
        "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "ADAPTIVE DIFFICULTY: INTERMEDIATE\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "This student has some footing in this topic. Use standard pacing —\n"
        "the default balance of intuition, formal definition, and worked\n"
        "example described in your response structure."
    ),
    "advanced": (
        "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "ADAPTIVE DIFFICULTY: ADVANCED\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "This student has shown consistent mastery on this topic. You may\n"
        "move faster, introduce more challenging variations or edge cases,\n"
        "skip basic re-derivations they've already seen, and lean less on\n"
        "the Socratic hand-holding — while still showing full work."
    ),
}


def _build_system_content(topic: str, difficulty: str) -> str:
    system_content = CAL_SYSTEM_PROMPT
    if topic:
        system_content += f"\n\n[PAGE CONTEXT: {topic}]"
    system_content += DIFFICULTY_GUIDANCE.get(difficulty, DIFFICULTY_GUIDANCE["intermediate"])
    return system_content


# Create OpenAI client (primary — xAI/Grok)
client = AsyncOpenAI(
    api_key=os.getenv("GROK_API_KEY"),
    base_url="https://api.x.ai/v1"
)


# ─────────────────────────────────────────────────────────────
# CB-20: Circuit breaker
# ─────────────────────────────────────────────────────────────
class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_seconds: int):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failure_count = 0
        self.state = "closed"
        self.opened_at = None

    def record_success(self):
        if self.state != "closed":
            logging.info("CIRCUIT_BREAKER: primary call succeeded, closing circuit")
        self.failure_count = 0
        self.state = "closed"
        self.opened_at = None

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold and self.state != "open":
            logging.warning(
                f"CIRCUIT_BREAKER: opening after {self.failure_count} consecutive primary failures"
            )
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.monotonic()

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.monotonic() - self.opened_at >= self.reset_seconds:
                self.state = "half_open"
                logging.info("CIRCUIT_BREAKER: reset window elapsed, trying half-open request")
                return True
            return False
        return True


_primary_circuit = CircuitBreaker(
    failure_threshold=CIRCUIT_FAILURE_THRESHOLD,
    reset_seconds=CIRCUIT_RESET_SECONDS,
)


# ─────────────────────────────────────────────────────────────
# CB-20: Response cache
# ─────────────────────────────────────────────────────────────
_response_cache: dict = {}


def _cache_key(message: str, topic: str, difficulty: str) -> str:
    raw = f"{(message or '').strip().lower()}|{(topic or '').strip().lower()}|{difficulty}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str):
    entry = _response_cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        _response_cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: str):
    _response_cache[key] = (time.monotonic() + LLM_CACHE_TTL_SECONDS, value)


def _build_messages(message: str, topic: str, difficulty: str, history: list, summary: str = "") -> list:
    messages = [{"role": "system", "content": _build_system_content(topic, difficulty)}]

    if summary and summary.strip():
        messages.append({
            "role": "system",
            "content": f"Earlier in this session: {summary}"
        })

    history = history[-10:] if history and len(history) > 10 else (history or [])
    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": message})
    return messages


async def ask_mock(
    message: str,
    topic: str = "",
    history: list = None,
    difficulty: str = "intermediate",
    summary: str = ""
):
    if history is None:
        history = []

    return f"""
Mock AI Response

Topic: {topic}
Difficulty (CB-18): {difficulty}
Session Summary (CB-13): {summary if summary else 'None'}

Question:
{message}

History Length:
{len(history)} messages

This is a placeholder response.
OpenAI integration will be used when USE_MOCK=False.
"""


async def ask_openai(
    message: str,
    topic: str = "",
    history: list = None,
    difficulty: str = "intermediate",
    summary: str = ""
):
    if history is None:
        history = []

    messages = _build_messages(message, topic, difficulty, history, summary)

    served_by = "primary"
    response_content = None

    if _primary_circuit.allow_request():
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model="grok-3-mini",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1000
                ),
                timeout=PRIMARY_TIMEOUT_SECONDS
            )
            response_content = response.choices[0].message.content
            _primary_circuit.record_success()
        except Exception as e:
            _primary_circuit.record_failure()
            logging.warning(f"PRIMARY_PROVIDER_FAILURE: {type(e).__name__}: {str(e)}")
    else:
        logging.info("CIRCUIT_BREAKER: open, skipping primary call and degrading to mock")

    if response_content is None:
        served_by = "fallback_mock"
        response_content = await ask_mock(message, topic, history, difficulty, summary)

    logging.info(f"LLM_RESPONSE_SOURCE: served_by={served_by} model={'grok-3-mini' if served_by == 'primary' else 'mock'}")

    # CB-8: Scope violation detection
    # Widened to match every topic in the SCOPE section of the system
    # prompt (added: continuity, linearization, chain rule, directional).
    calculus_keywords = [
        "derivative", "integral", "gradient", "limit", "vector",
        "lagrange", "taylor", "partial", "curl", "divergence",
        "multivariable", "calculus", "differentiate", "integrate",
        "continuity", "continuous", "linearization", "chain rule",
        "directional", "tangent plane", "constrained optimization"
    ]

    has_calculus_keyword = any(kw in message.lower() for kw in calculus_keywords)
    has_cal_refusal = "I'm Cal" in response_content

    if not has_cal_refusal and not has_calculus_keyword:
        logging.warning(f"SCOPE_VIOLATION: possible off-topic response for message: {message[:80]}")

    return response_content


async def ask_mock_stream(
    message: str,
    topic: str = "",
    history: list = None,
    difficulty: str = "intermediate",
    summary: str = ""
):
    import asyncio

    if history is None:
        history = []

    summary_note = f" Session summary (CB-13): {summary}." if summary else ""

    full_text = (
        f"Mock streamed response. Topic: {topic or 'general'}. "
        f"Difficulty (CB-18): {difficulty}.{summary_note} "
        f"You asked: {message}. "
        f"History length: {len(history)} messages. "
        f"This is a placeholder streamed response simulating real token output."
    )

    for word in full_text.split(" "):
        yield word + " "
        await asyncio.sleep(0.03)


async def ask_openai_stream(
    message: str,
    topic: str = "",
    history: list = None,
    difficulty: str = "intermediate",
    summary: str = ""
):
    if history is None:
        history = []

    messages = _build_messages(message, topic, difficulty, history, summary)

    got_any_token = False

    if _primary_circuit.allow_request():
        try:
            stream = await asyncio.wait_for(
                client.chat.completions.create(
                    model="grok-3-mini",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1000,
                    stream=True,
                ),
                timeout=PRIMARY_TIMEOUT_SECONDS
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    got_any_token = True
                    yield delta
            _primary_circuit.record_success()
            logging.info("LLM_RESPONSE_SOURCE: served_by=primary model=grok-3-mini (stream)")
            return
        except Exception as e:
            _primary_circuit.record_failure()
            logging.warning(f"PRIMARY_PROVIDER_FAILURE (stream): {type(e).__name__}: {str(e)}")
            if got_any_token:
                return
    else:
        logging.info("CIRCUIT_BREAKER: open, skipping primary stream and degrading to mock")

    logging.info("LLM_RESPONSE_SOURCE: served_by=fallback_mock (stream)")
    async for chunk in ask_mock_stream(message, topic, history, difficulty, summary):
        yield chunk


async def ask_llm_stream(
    message: str,
    topic: str = "",
    history: list = None,
    difficulty: str = "intermediate",
    summary: str = ""
):
    cache_key = _cache_key(message, topic, difficulty)
    cached = _cache_get(cache_key)
    if cached is not None:
        logging.info("LLM_RESPONSE_SOURCE: served_by=cache (stream)")
        for word in cached.split(" "):
            yield word + " "
            await asyncio.sleep(0.01)
        return

    chunks = []
    if USE_MOCK:
        async for chunk in ask_mock_stream(message, topic, history, difficulty, summary):
            chunks.append(chunk)
            yield chunk
    else:
        async for chunk in ask_openai_stream(message, topic, history, difficulty, summary):
            chunks.append(chunk)
            yield chunk

    if chunks:
        _cache_set(cache_key, "".join(chunks))


async def ask_llm(
    message: str,
    topic: str = "",
    history: list = None,
    difficulty: str = "intermediate",
    summary: str = ""
):
    cache_key = _cache_key(message, topic, difficulty)
    cached = _cache_get(cache_key)
    if cached is not None:
        logging.info("LLM_RESPONSE_SOURCE: served_by=cache")
        return cached

    if USE_MOCK:
        result = await ask_mock(message, topic, history, difficulty, summary)
    else:
        result = await ask_openai(message, topic, history, difficulty, summary)

    _cache_set(cache_key, result)
    return result


SUMMARY_PROMPT = """Compress this calculus tutoring conversation into a 3-5 sentence
running summary. Note topics covered, where the student struggled, and what
was already explained. Do not include LaTeX or follow-up suggestions."""


async def summarize_history(messages: list, previous_summary: str = "") -> str:
    content = f"Previous summary: {previous_summary}\n\n" if previous_summary else ""
    content += "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    response = await client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.2,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()