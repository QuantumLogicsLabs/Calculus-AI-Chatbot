# CalcVoyager tests

Run all commands from the repository root after installing both Python requirements files.
Use `.venv/bin/python` on Linux/macOS instead of the Windows path below.

## Offline CI checks (no API key)

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=test-results/mock.xml
```

`conftest.py` forces mock mode before imports, clears the Groq key in the test
process, rejects real provider paths, and resets the cache per test. Database
checks use temporary SQLite files and real production database helpers; they do
not replace those helpers with fake SQL implementations. Authentication identity
is patched where user isolation is under test. These tests do not validate the
placeholder token authentication or claim real-model mathematical accuracy.

Coverage includes:

- Real backend feedback route: valid votes, persisted rows, upserts, bad input,
  guests, wrong users, wrong sessions and nonexistent messages.
- Backend-to-AI HTTP contracts via ASGI transports: JSON, SSE completion, supplied
  history, persisted turns, history retrieval, exports, validation and rate limits.
- Conversation history, page topic, difficulty and summary reaching the actual
  prompt builder through the AI route, using a recording model stub.
- Existing cache regressions, with explicit assertions on their returned results.
- Mock streaming latency, missing/late token failures and nonzero latency gates.
- Evaluation validators and exit codes. A subprocess test proves that placeholder
  replies make the real quality-evaluation CLI exit 1 instead of silently passing.

`pytest.ini` discovers the offline suites in `tests` and `aiService/tests`.
`chatbot_tests.py` is an explicit real-evaluation module, not a pytest test file.
The root `test_stream.py` is an import-safe manual live-server probe.

## Real Groq evaluation (optional; consumes API credits)

Use your ignored `aiService/services/.env` file for `GROQ_API_KEY` and set
`USE_MOCK=False`. Do not edit the Python source to switch providers or modes.
Existing shell environment variables take priority over `.env` values.

```powershell
$env:USE_MOCK = "False"
.\.venv\Scripts\python.exe -m aiService.tests.chatbot_tests
.\.venv\Scripts\python.exe -m aiService.tests.test_streaming_latency
```

The client calls Groq, not xAI/Grok. `GROK_API_KEY` does not configure this client.
The model defaults to `openai/gpt-oss-120b` and can be set with `GROQ_MODEL`.
Real-provider errors raise safe errors; they never fall back to mock replies.
Offline provider tests use stubs to cover failures, empty/truncated streams,
timeouts, circuit recovery, cancellation, cache isolation and error redaction.

The response-quality module checks its existing thresholds: CB-2 at least 18/20
formatting/length passes, CB-8 10/10 refusals, CB-9 at least 16 answer-key matches
at score >= 0.6, and the follow-up-cache regressions. A confirmed incorrect boxed
answer fails that question through independent SymPy verification. Answer-key
matching is an automated heuristic, not proof of mathematical correctness.
The latency module requires a nonempty first token within 2 seconds for every
sample. Failed gates exit nonzero. Mock answers are expected to fail real quality
acceptance; offline CI tests the application contracts separately.

Fresh reports go to `test-results/` (ignored), or the directory selected with
`CALCVOYAGER_TEST_RESULTS_DIR`. CI never reads the old tracked result snapshots
in `aiService/tests/test_results.json` or `scope_results.json` as pass evidence.

## GitHub Actions

- Push/PR offline jobs test Python 3.11 and 3.12 with no secrets.
- A separate job installs the frontend lockfile, runs service/UI/rendering tests,
  and builds with `CI=true`. CRA's Jest resolver uses explicit CommonJS mappings
  for the locked React Router package.
- The nightly or explicitly selected real evaluation requires the team-owned
  `GROQ_API_KEY` repository secret; missing credentials fail clearly.
- Test/evaluation commands do not suppress failures. JUnit reports are uploaded
  even when offline tests fail.
- Existing SnapDeploy deployment is manual-only: on `main`, explicitly select
  `deploy_backend` in Run workflow. Offline tests and frontend build must pass,
  and SnapDeploy secrets must be configured. Ordinary pushes do not redeploy it.

No real API calls, remote CI runs, or hosting changes are needed for local offline
verification. The runtime dependency deprecation warnings are reported separately
from test failures.

## Two-question live smoke check

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_live_chat --backend-url http://127.0.0.1:8002
```

Run against your restarted, real-mode local backend. This requires two distinct,
fresh primary-provider answers and independent boxed math verification. The
ignored `test-results/live-smoke.json` report retains returned answers and parser
diagnostics even if verification fails. An unsupported notation is unverified,
not automatically an incorrect mathematical answer. This does not certify the
entire model or the inaccessible production deployment.
