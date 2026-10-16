"""Serve the bundled React app without masking missing API or asset routes."""
from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        path = path.replace("\\", "/").lstrip("/")
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if (exc.status_code != 404 or scope["method"] not in {"GET", "HEAD"}
                    or path.split("/", 1)[0] in {"api", "health", "static"}
                    or PurePosixPath(path).suffix):
                raise
            response = await super().get_response("index.html", scope)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response
