"""
Password reset OTP service (no SMTP).

Flow:
- Generate OTP
- Hash OTP and store in DB with expiration
- Validate OTP for reset
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

from api.auth.password_utils import hash_password, verify_password
from database.app_store import (
    create_otp_token,
    get_latest_active_otp_token,
    list_recent_otp_tokens,
    mark_otp_used,
)


OTP_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_OTP_TTL_MINUTES", "5"))
OTP_RATE_LIMIT_PER_HOUR = int(os.getenv("PASSWORD_RESET_OTP_RATE_LIMIT_PER_HOUR", "3"))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_otp() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


def _is_expired(expires_at_iso: str) -> bool:
    expires_at = datetime.fromisoformat(expires_at_iso)
    return expires_at <= _now_utc()


def create_reset_otp(user_id: str) -> tuple[str, str]:
    since = (_now_utc() - timedelta(hours=1)).isoformat()
    recent = list_recent_otp_tokens(user_id=user_id, since_iso=since)
    if len(recent) >= OTP_RATE_LIMIT_PER_HOUR:
        raise ValueError("Too many OTP requests. Try again later.")

    otp = _build_otp()
    expires_at = (_now_utc() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()
    otp_hash = hash_password(otp)

    create_otp_token(
        user_id=user_id,
        otp_hash=otp_hash,
        expires_at=expires_at,
    )

    return otp, expires_at


def verify_reset_otp(user_id: str, otp: str) -> tuple[bool, str]:
    token = get_latest_active_otp_token(user_id=user_id)
    if not token:
        return False, "OTP expired or not found"

    if _is_expired(token["expires_at"]):
        return False, "OTP expired"

    if not verify_password(otp, token["otp_hash"]):
        return False, "Invalid OTP"

    return True, token["id"]


def invalidate_reset_otp(token_id: str) -> None:
    mark_otp_used(token_id)
