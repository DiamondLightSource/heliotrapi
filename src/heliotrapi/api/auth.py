import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from heliotrapi.config import AuthConfig

# auto_error=False so requests without credentials still reach require_auth,
# which lets the endpoints stay open when auth is disabled
security = HTTPBasic(auto_error=False)


def require_auth(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> str | None:
    """Checks HTTP Basic credentials against the config.
    Returns the username, or None if auth is disabled"""

    auth_config: AuthConfig = request.app.state.config.auth

    if not auth_config.enabled:
        return None

    if credentials is not None:
        # compare_digest on both so the check takes the same time either way
        username_ok = secrets.compare_digest(
            credentials.username.encode(), auth_config.username.encode()
        )
        password_ok = secrets.compare_digest(
            credentials.password.encode(), auth_config.password.encode()
        )
        if username_ok and password_ok:
            return credentials.username

    # the WWW-Authenticate header makes browsers show their login prompt
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Basic"},
    )
