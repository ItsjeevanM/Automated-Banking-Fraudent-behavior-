"""
auth.py  (ROOT LEVEL — JWT utilities)
============================================================
This file lives at:  backend/auth.py
NOT inside routes/

It is imported by:
  routes/auth.py    → register/login/logout endpoints
  routes/upload.py  → get_current_user dependency
  routes/reports.py → get_current_user dependency

Functions:
  hash_password()         bcrypt hash
  verify_password()       bcrypt verify
  create_access_token()   JWT 15 min
  create_refresh_token()  JWT 7 days
  decode_token()          verify + decode
  get_current_user()      FastAPI dependency
  logout_token()          add to blocklist
============================================================
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from database import blocklist_token, get_user_by_id, is_token_blocked

# ── Config ────────────────────────────────────────────────────
JWT_SECRET: str  = os.getenv("JWT_SECRET", "bankforensiq-secret-change-this")
ALGORITHM:  str  = "HS256"
ACCESS_EXPIRE_MINUTES: int = 15
REFRESH_EXPIRE_DAYS:   int = 7

# ── Bcrypt context ────────────────────────────────────────────
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# ── HTTP Bearer scheme ────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


# ══════════════════════════════════════════════════════════════
# PASSWORD
# ══════════════════════════════════════════════════════════════

def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ══════════════════════════════════════════════════════════════
# TOKENS
# ══════════════════════════════════════════════════════════════

def create_access_token(user_id: str, email: str, role: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub":   user_id,
        "email": email,
        "role":  role,
        "jti":   str(uuid.uuid4()),
        "exp":   now + timedelta(minutes=ACCESS_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub":  user_id,
        "jti":  str(uuid.uuid4()),
        "exp":  now + timedelta(days=REFRESH_EXPIRE_DAYS),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ══════════════════════════════════════════════════════════════
# FastAPI DEPENDENCY
# ══════════════════════════════════════════════════════════════

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload  = decode_token(credentials.credentials)
    jti      = payload.get("jti")
    user_id  = payload.get("sub")

    if not jti or not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    if is_token_blocked(jti):
        raise HTTPException(status_code=401, detail="Token revoked. Please log in again.")

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return user


# ══════════════════════════════════════════════════════════════
# LOGOUT
# ══════════════════════════════════════════════════════════════

def logout_token(token: str) -> None:
    payload    = decode_token(token)
    jti        = payload.get("jti")
    exp        = payload.get("exp")
    if not jti or exp is None:
        return
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
    blocklist_token(jti, expires_at)