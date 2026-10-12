"""python -m api  — run the server with the settings in api/config.py."""

import uvicorn

from .config import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        ws_ping_interval=settings.ws_ping_interval,
        ws_ping_timeout=settings.ws_ping_timeout,
        log_level="info",
    )
