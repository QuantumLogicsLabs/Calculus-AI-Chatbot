import subprocess
import sys

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount
from starlette.testclient import TestClient

from backend.app.auth.auth_utils import require_user
from backend.app.frontend import FrontendFiles
from backend.app.routes.chat import RateLimiter
from scripts.serve_render import server_command, stop_children


def test_frontend_routes_do_not_mask_missing_api_or_assets(tmp_path):
    (tmp_path / "index.html").write_text("<html>CalcVoyager</html>")
    (tmp_path / "bundle.js").write_text("console.log('ok')")
    app = Starlette(routes=[Mount("/", app=FrontendFiles(directory=tmp_path, html=True))])
    with TestClient(app) as client:
        for path in ("/", "/calculus/derivatives"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
        assert client.get("/bundle.js").status_code == 200
        for path in ("/api/missing", "/api", "/health", "/static/missing", "/missing.js"):
            assert client.get(path).status_code == 404


def test_preview_rejects_placeholder_login_and_spoofed_ip(monkeypatch):
    monkeypatch.setenv("CALCVOYAGER_PREVIEW", "True")
    request = Request({"type": "http", "headers": [
        (b"authorization", b"Bearer pretend-login"),
        (b"x-forwarded-for", b"attacker-controlled")], "client": ("127.0.0.1", 123)})
    assert require_user(request) is None
    assert RateLimiter()._get_guest_key(request) == "guest_127.0.0.1"


def test_server_has_one_worker_and_does_not_trust_proxy_headers():
    command = server_command("backend.app.main:app", "0.0.0.0", 10000)
    assert command[:3] == [sys.executable, "-m", "uvicorn"]
    assert command[-1] == "--no-proxy-headers"
    assert "--workers" not in command


def test_supervisor_reaps_a_running_child():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        stop_children([child])
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
