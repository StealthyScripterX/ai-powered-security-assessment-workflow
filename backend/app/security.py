"""Authentication and server-side RBAC foundation.

Phase 1 stand-in for the OIDC integration architecture/TASD-v1.0.md section
8.3 specifies: local username/password + a server-issued JWT. This is a
declared, documented deviation (see IMPLEMENTATION-NOTES.md), not a
silent architecture change -- the contract RBAC depends on (role is
server-derived, never client-supplied) is preserved regardless of the
transport:

 - `hash_password` / `verify_password`: bcrypt via passlib.
 - `create_access_token`: signs {sub, role} with JWT_SECRET_KEY (never
   hardcoded -- app/config.py reads it from the environment; if unset,
   token issuance is refused rather than falling back to a guessable
   default).
 - `get_current_user`: the ONLY place a request's actor identity and role
   are established. Every service function receives `actor_id`/`role`
   from this dependency's output, never from a request body field --
   this is the literal implementation of D2 section 9.2 / D4 section 7 / D5
   section 5's "actor identity is never a client-supplied field," applied
   this early because it is the one rule every later phase's endpoints
   will also depend on.
 - `require_role`: a dependency factory for per-endpoint RBAC -- "enforce
   authorization on the server, not just the UI."
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import AppUser, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


class AuthNotConfiguredError(RuntimeError):
    """Raised when JWT_SECRET_KEY is unset.

    Deliberately an explicit refusal, not a fallback to a hardcoded or
    guessable signing key -- "never hardcode API keys or secrets."
    """


def create_access_token(*, subject: str, role: UserRole) -> str:
    settings = get_settings()
    if not settings.auth_configured:
        raise AuthNotConfiguredError(
            "JWT_SECRET_KEY is not configured. Set it in the environment (see .env.example) "
            "before issuing tokens."
        )
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role.value, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


class CurrentUser:
    def __init__(self, user_id: str, role: UserRole):
        self.user_id = user_id
        self.role = role


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not settings.auth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server (JWT_SECRET_KEY unset).",
        )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        role_value = payload.get("role")
        if user_id is None or role_value is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    result = await db.execute(select(AppUser).where(AppUser.id == user_id, AppUser.is_active == True))  # noqa: E712
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    # Role is re-read from the database record, not trusted from the token
    # claim alone -- a role change by a Platform Owner takes effect on the
    # next request rather than waiting for token expiry.
    return CurrentUser(user_id=user.id, role=user.role)


def require_role(*allowed: UserRole):
    """Dependency factory: 403s any caller whose server-derived role is
    not in `allowed`. Used per-endpoint, e.g.
    `Depends(require_role(UserRole.REQUESTER))`.
    """

    async def _check(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current.role.value} is not permitted to perform this action.",
            )
        return current

    return _check
