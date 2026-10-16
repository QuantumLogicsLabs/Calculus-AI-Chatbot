"""Two-question live smoke check. Run only after configuring a real Groq key.

python -m scripts.verify_live_chat --backend-url http://127.0.0.1:8002
This makes exactly two chat requests on success; it does not deploy anything.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from aiService.services.math_verifier import verify_cal_math

QUESTIONS = ("Find the derivative of x**3", "Find the derivative of sin(x)")


def verify(client, backend_url, results=None):
    results = [] if results is None else results
    run_id = str(uuid4())  # Separate context avoids a stale cache passing as live evidence.
    for question in QUESTIONS:
        response = client.post(backend_url.rstrip("/") + "/api/chat/", json={
            "messages": [{"role": "user", "content": question}],
            "context": "Calculus live verification " + run_id, "topic_key": "calculus",
        })
        if response.status_code != 200:
            raise RuntimeError(f"Chat request failed with HTTP {response.status_code}; inspect service logs.")
        data = response.json()
        if data.get("mode") != "live" or data.get("source") != "primary":
            raise RuntimeError("Expected a fresh live-provider answer; mock, cache or missing source cannot pass.")
        reply = data.get("reply", "")
        if not isinstance(reply, str) or not reply.strip():
            raise RuntimeError("The tutor returned an empty answer.")
        correct, expected, diagnostic = verify_cal_math(question, reply)
        results.append({"question": question, "reply": reply, "mode": data["mode"],
                        "source": data["source"], "math_verified": correct is True,
                        "expected": expected, "diagnostic": diagnostic})
        if correct is not True:
            raise RuntimeError("Could not verify the boxed result. Inspect the saved response and parser diagnostic before judging accuracy.")
    if results[0]["reply"].strip() == results[1]["reply"].strip():
        raise RuntimeError("Different questions returned identical answers.")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    output = Path("test-results/live-smoke.json")
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": False, "results": []}
    try:
        with httpx.Client(timeout=45) as client:
            verify(client, args.backend_url, report["results"])
        report["passed"] = True
        print("PASS: two distinct fresh live answers with independently verified boxed results.")
    except (RuntimeError, httpx.HTTPError, ValueError) as exc:
        # HTTP status and our own validation messages are safe; avoid provider bodies/URLs.
        report["error"] = str(exc) if isinstance(exc, RuntimeError) else "Could not verify the backend response."
        print("FAIL: " + report["error"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
