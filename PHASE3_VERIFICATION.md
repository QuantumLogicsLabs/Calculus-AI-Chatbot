# Phase 3 verification - 16 October 2026

Scope: remove silent mock fallback in real mode and verify the local chat path.
All changes remain on `codex/chatbot-fixes`; no hosting deployment was performed.

## Resulting behavior

- Real mode is the default. Missing Groq credentials or invalid settings fail
  startup. `.env.example` explicitly opts into an offline demo.
- Mock mode is logged and labelled in the UI. Live failures never return demo text.
- Provider failures, timeouts, empty output and incomplete/truncated streams
  produce safe JSON or SSE errors. Provider exception bodies are not exposed.
- Idle/total stream deadlines, provider stream cleanup and a single half-open
  circuit probe bound the failure path. SDK retries are disabled.
- Only complete responses enter the cache or persisted conversation. Cache keys
  include exact-case question/history, summary, model and mode.
- The frontend treats missing completion markers as errors. It discards partial
  answers and never retries provider failures or 429s automatically. Only HTTP
  404/405/501 allow one legacy JSON retry when streaming is unsupported.
- Live display math no longer nests a block element inside a paragraph.

## Final checks

- Python 3.12: 94 tests passed, zero failures/errors/skips.
- Frontend: 20 tests passed across three suites.
- `CI=true` production build compiled successfully.
- `git diff --check` passed.
- Credential audit found no supplied key in tracked or unignored source files.
- Main local services now run on ports 3000/8002/8001; AI health reports live mode.
  Temporary QA services were stopped after verification.

## Evidence

- Offline Python tests cover success and negative provider paths, actual AI and
  backend contracts, persistence, verification gates and legacy behavior.
- Frontend tests cover SSE fragmentation, explicit errors, empty/truncated streams,
  timeout aborts, retry limits, error UI, demo labels and display-math DOM structure.
- Browser QA on isolated localhost ports confirmed a mock response and visible
  demo label. Stopping only that QA AI service produced a visible error and just
  one backend stream request, with no JSON retry.
- The provided key was initially entered in `.env.example`. It was moved into
  ignored `aiService/services/.env`; the example was sanitized without printing it.
- Two recorded real Groq answers came from `primary` in `live` mode: the derivative
  of `x**3` was `3*x**2`, and the derivative of `sin(x)` was `cos(x)`.
- The second answer used standard LaTeX `\cos(x)`. A narrow verifier normalization
  fixed its parsing; both saved live answers then passed independent verification
  without new API calls. Unsupported notation now returns no verdict rather than
  being incorrectly classified as a wrong calculation.
- A real browser stream completed successfully; AI/backend logs both recorded
  `primary` / `live`. No demo label remained after the live completion.

Local evidence: `test-results/live-smoke.json`, `test-results/mock.xml` and QA
logs/screenshots under `.cache/`. Credentials and generated reports are ignored.

## Practical limits

These checks establish the repaired local path and the recorded sample answers.
They do not establish the cause of the inaccessible SnapDeploy deployment or
certify all model answers. Complete authentication, certificates, session-history
UI, follow-up extraction and parallel production hosting remain separate scope.
The full scheduled 30-question real quality suite was not run with a personal key.
