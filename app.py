"""SnapDeploy entrypoint — listen on port 3000 (platform default)."""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=port,
    )
