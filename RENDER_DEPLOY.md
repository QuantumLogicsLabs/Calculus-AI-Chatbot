# Free Render preview

This deployment runs React, the API and a private AI worker in one Docker web
service. It is a guest-chat preview. The repository's placeholder authentication
is disabled here; saved sessions and authenticated feedback are unavailable.
Do not disable `CALCVOYAGER_PREVIEW` until real authentication is implemented.

## Render settings

1. New > Web Service > Git Provider. Connect GitHub and choose
   `mustfaaaa/Calculus-AI-Chatbot`.
2. Branch: `codex/chatbot-fixes`. Root directory: leave blank.
3. Language/runtime: Docker. Dockerfile path: `./Dockerfile`.
4. Instance type: **Free**. Do not add a disk, paid database or paid instance.
5. Health check path: `/health`. Leave Docker command blank.
6. Environment variables:

   | Name | Value |
   | --- | --- |
   | `GROQ_API_KEY` | Your private Groq key; enter only in Render's environment settings |
   | `USE_MOCK` | `False` |
   | `GROQ_MODEL` | `openai/gpt-oss-120b` |
   | `CALCVOYAGER_PREVIEW` | `True` |

7. Deploy Web Service. Keep the build and runtime logs open.

The Docker image builds the frontend with same-origin API URLs. Do not set
`REACT_APP_API_URL`, `REACT_APP_CHAT_URL` or `AI_SERVICE_URL` for this deployment.
Local `.env` files and keys are excluded from the Docker context. The secret
must be entered in Render even if local chat already works.

## Verify before sharing

Open the new `https://...onrender.com` URL and ask two different calculus
questions. Answers should differ, match the questions, and stream to completion.
Logs should show `LLM_RESPONSE_SOURCE` with `mode=live` and `served_by=primary`
for fresh questions. `/health` checks the web process; it does not validate Groq
credentials, quota or model availability. Provider failures must show an error
instead of a canned reply.

Optional explicit real-provider check (two Groq requests):

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_live_chat --backend-url https://YOUR-SERVICE.onrender.com
```

## Free plan limits

Render sleeps an idle free service after 15 minutes and waking can take around
a minute. Files, caches and rate-limit counters reset on restart; no durable
chat history is promised. Free hours and outbound bandwidth are limited across
the workspace. Groq has its own quota. Guest traffic is limited to 10 requests
per hour per observed network address; Render proxy addresses may cause users
to share that limit. This is a preview, not a production authentication setup.

References: https://render.com/docs/free and https://render.com/docs/docker.

## Local check of the bundled service

Build the frontend with `REACT_APP_API_URL` and `REACT_APP_CHAT_URL` set to empty
strings. Set `FRONTEND_BUILD_DIR` to its absolute build path, then run:

```powershell
$env:FRONTEND_BUILD_DIR = 'C:\Calculus-AI-Chatbot\frontend\build'
$env:PORT = '10000'
.\.venv\Scripts\python.exe -m scripts.serve_render
```

The private AI port defaults to 8001; stop another local AI instance first or
set `INTERNAL_AI_PORT` to a free port. `USE_MOCK=True` is only for an explicit
offline check. A Docker image build still needs Docker or Render's build server.
