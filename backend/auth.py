"""Optional access gate for a shared / public deployment.

When STUDIO_PASSWORD is set, every request must carry the right credentials
(HTTP Basic - the username is ignored, only the password is checked). When it is
NOT set, the app requires ALLOW_OPEN_LOCAL=1 to permit access (fail closed for
production security).

This is a single shared password, meant for "share the URL + password with a few
people." For real multi-user auth, use the Next.js + Supabase team UI in web/.
Always run a public instance behind TLS (a reverse proxy) so Basic creds are not
sent in the clear.
"""

import base64
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

# Paths that stay open even when a password is set (health check + the login realm).
_OPEN_PATHS = {"/api/health"}


def _expected() -> str:
    return os.environ.get("STUDIO_PASSWORD", "").strip()


def _allow_open_local() -> bool:
    """Check if dev mode with no auth is allowed (ALLOW_OPEN_LOCAL=1)."""
    return os.environ.get("ALLOW_OPEN_LOCAL", "").strip() == "1"


def _check(header: str, password: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8", "replace")
    except Exception:
        return False
    # "username:password" - username ignored, constant-time compare on the password
    _, _, supplied = decoded.partition(":")
    return hmac.compare_digest(supplied, password)


class AccessPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        password = _expected()

        # If path is always open, allow it
        if request.url.path in _OPEN_PATHS:
            return await call_next(request)

        # If password is configured, check it
        if password:
            auth = request.headers.get("Authorization", "")
            if _check(auth, password):
                return await call_next(request)
        # If no password and dev mode is enabled, allow it
        elif _allow_open_local():
            return await call_next(request)
        # No password configured and dev mode disabled: fail closed (production default)
        else:
            if request.headers.get("accept", "").find("text/html") != -1:
                return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="ZAO Studio"'})
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        # Browser-native prompt for page loads; JSON for API clients.
        if request.headers.get("accept", "").find("text/html") != -1:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="ZAO Studio"'})
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
