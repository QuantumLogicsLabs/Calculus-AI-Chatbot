import time
import httpx

URL = "http://127.0.0.1:8002/api/chat/stream"
BODY = {"messages": [{"role": "user", "content": "what is a derivative"}]}

def main():
    start = time.monotonic()

    with httpx.Client(timeout=45) as client:
        with client.stream("POST", URL, json=BODY) as r:
            print(f"status: {r.status_code}\n")
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                elapsed = time.monotonic() - start
                print(f"[{elapsed:6.3f}s] {line}")

    print(f"\ndone in {time.monotonic() - start:.3f}s")


if __name__ == "__main__":
    main()
