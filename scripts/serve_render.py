"""Run the private AI worker and public web app in one Render container."""
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request


def server_command(module, host, port):
    return [sys.executable, "-m", "uvicorn", module, "--host", host,
            "--port", str(port), "--no-proxy-headers"]


def stop_children(children):
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 8
    for child in children:
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def main():
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    ai_port = int(os.getenv("INTERNAL_AI_PORT", "8001"))
    public_port = int(os.getenv("PORT", "10000"))
    if ai_port == public_port:
        raise ValueError("Public and private ports must differ")
    env = os.environ.copy()
    env["AI_SERVICE_URL"] = f"http://127.0.0.1:{ai_port}"
    # Explicit opt-in to mock mode is supported for local deployment checks.
    env.setdefault("USE_MOCK", "False")
    env.setdefault("CALCVOYAGER_PREVIEW", "True")
    try:
        ai = subprocess.Popen(server_command("aiService.chatbot:app", "127.0.0.1", ai_port), env=env)
        children.append(ai)
        deadline = time.monotonic() + 60
        while not stopping:
            if ai.poll() is not None:
                return 1
            try:
                with urllib.request.urlopen(env["AI_SERVICE_URL"] + "/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                pass
            if time.monotonic() >= deadline:
                print("AI worker did not become ready", file=sys.stderr)
                return 1
            time.sleep(0.2)
        if stopping:
            return 0
        children.append(subprocess.Popen(
            server_command("backend.app.main:app", "0.0.0.0", public_port), env=env))
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("A service exited; stopping the container", file=sys.stderr)
                return 1
            time.sleep(0.2)
        return 0
    finally:
        stop_children(children)


if __name__ == "__main__":
    raise SystemExit(main())
