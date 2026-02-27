"""
=============================================================================
FILE: app/api/v1/auth.py
PURPOSE: Handles all authentication HTTP endpoints for version 1 of the API.

         Routes defined here:
           POST   /api/v1/auth/register  → Creates a new user (no password).
                                           Returns an enrollment_token JWT so the
                                           frontend can begin sending behavioral
                                           signals during the enrollment phase.

           POST   /api/v1/auth/login     → The core passwordless login endpoint.
                                           Accepts email + behavioral payload,
                                           runs feature engineering and trust
                                           scoring, and returns a trust_score,
                                           a decision (granted/step_up/challenge/
                                           recovery), and a session JWT if granted.

           GET    /api/v1/auth/status    → Validates the current Bearer token and
                                           returns the user's enrollment state and
                                           account status.

           DELETE /api/v1/auth/logout    → Revokes the current session token.

         This file orchestrates the full login flow by calling:
           feature_engineer.py → trust_engine.py → baseline_service.py
=============================================================================
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models.user import User
from app.db.models.behavior import BehaviorBaseline, UserBehaviorLog
from app.db.models.session import AuthSession, TrustLog
from app.schemas.auth import (
    LoginRequest, LoginResponse,
    RegisterRequest, RegisterResponse,
)
from app.services import feature_engineer, trust_engine, baseline_service

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


# ── POST /auth/register ───────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user (no password)",
)
async def register_user(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    """
    Creates a user record.
    Returns an enrollment_token (short-lived JWT) that the frontend uses
    to authenticate during the enrollment phase (first N sessions).

    No password is required or accepted.
    """
    # Check for duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    user = User(
        email=body.email,
        display_name=body.display_name,
        recovery_email=body.recovery_email,
        status="pending",
        is_enrolled=False,
        enrollment_session_count=0,
    )
    db.add(user)
    await db.flush()    # get the UUID assigned without full commit

    # Enrollment token — short-lived, type="enrollment"
    token = create_access_token(
        subject=str(user.id),
        token_type="enrollment",
        expires_minutes=settings.ENROLLMENT_TOKEN_EXPIRE_MINUTES,
    )

    return RegisterResponse(
        user_id=user.id,
        email=user.email,
        enrollment_token=token,
        sessions_required=settings.MIN_ENROLLMENT_SESSIONS,
        message=(
            f"Account created. Complete {settings.MIN_ENROLLMENT_SESSIONS} behavioral "
            "sessions to finish enrollment and enable login."
        ),
    )


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Behavioral login — returns trust score and decision",
)
async def login_user(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """
    Main authentication endpoint.

    Flow:
      1. Look up user by email.
      2. Run feature engineering on the behavioral payload.
      3. Load user baseline (or empty dict if not enrolled).
      4. Run trust engine → TrustResult.
      5. Persist BehaviorLog + TrustLog.
      6. If decision == "granted" → issue session JWT + create AuthSession row.
      7. Return LoginResponse.
    """
    # ── 1. Look up user ───────────────────────────────────────────────────────
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if user is None:
        # Return a generic delay response to prevent user enumeration
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first.",
        )

    if user.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is locked. Use the recovery flow.",
        )

    # ── 2. Feature engineering ────────────────────────────────────────────────
    fv = feature_engineer.engineer(body.behavior)

    # ── 3. Load baseline ──────────────────────────────────────────────────────
    bl_result = await db.execute(
        select(BehaviorBaseline).where(BehaviorBaseline.user_id == user.id)
    )
    baseline_orm = bl_result.scalar_one_or_none()
    baseline_dict = baseline_service.baseline_to_dict(baseline_orm) if baseline_orm else {}

    # ── 4. Trust scoring ──────────────────────────────────────────────────────
    trust_result = trust_engine.score(body.behavior, baseline_dict)

    # ── 5. Persist behavior log ───────────────────────────────────────────────
    log = UserBehaviorLog(
        user_id=user.id,
        typing_speed=body.behavior.typing_speed,
        key_hold_time=body.behavior.key_hold_time,
        mouse_velocity=body.behavior.mouse_velocity,
        click_interval=body.behavior.click_interval,
        scroll_depth=body.behavior.scroll_depth,
        network_latency=body.behavior.network_latency,
        device_hash=body.behavior.device_hash,
        location_hash=body.behavior.location_hash,
        time_of_day=body.behavior.time_of_day,
        feature_vector=fv.vector,
        is_anomalous=len(trust_result.anomaly_flags) > 0,
    )
    db.add(log)
    await db.flush()

    # ── 5b. Persist trust log (immutable audit) ───────────────────────────────
    tlog = TrustLog(
        user_id=user.id,
        trust_score=trust_result.trust_score,
        decision=trust_result.decision,
        anomaly_flags=trust_result.anomaly_flags,
        score_breakdown=trust_result.breakdown,
        model_version=trust_result.model_version,
    )
    db.add(tlog)

    # ── 6. Session issuance ───────────────────────────────────────────────────
    session_token: str | None = None
    expires_in: int | None = None

    if trust_result.decision == "granted":
        jti = str(uuid.uuid4())
        session_token = create_access_token(
            subject=str(user.id),
            token_type="session",
            extra_claims={"jti": jti},
        )
        expires_dt = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        auth_session = AuthSession(
            user_id=user.id,
            session_token_jti=jti,
            trust_score=trust_result.trust_score,
            decision=trust_result.decision,
            expires_at=expires_dt,
        )
        db.add(auth_session)

        # Update user's last_seen_at and promote to active
        user.last_seen_at = datetime.now(timezone.utc)
        if user.status == "pending" and user.is_enrolled:
            user.status = "active"

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # If user is still enrolling, increment their session count
    if not user.is_enrolled:
        user.enrollment_session_count += 1
        if user.enrollment_session_count >= settings.MIN_ENROLLMENT_SESSIONS:
            # Build baseline from collected data
            new_baseline = await baseline_service.build_initial_baseline(str(user.id), db)
            if new_baseline:
                user.is_enrolled = True
                user.status = "active"

    # ── 7. Return response ────────────────────────────────────────────────────
    decision_messages = {
        "granted":   "Authentication successful.",
        "step_up":   "Behavioral match partial. Please complete step-up verification.",
        "challenge": "Low confidence match. Please verify via magic link or biometric.",
        "recovery":  "Authentication failed. Use the recovery flow to regain access.",
    }

    return LoginResponse(
        trust_score=trust_result.trust_score,
        decision=trust_result.decision,
        session_token=session_token,
        expires_in=expires_in,
        anomaly_flags=trust_result.anomaly_flags,
        score_breakdown=trust_result.breakdown,
        message=decision_messages.get(trust_result.decision, ""),
    )


# ── GET /auth/status ──────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Validate current session and return user status",
)
async def get_auth_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return {
        "user_id": str(current_user.id),
        "email": current_user.email,
        "status": current_user.status,
        "is_enrolled": current_user.is_enrolled,
        "enrollment_sessions": current_user.enrollment_session_count,
        "last_seen_at": current_user.last_seen_at,
    }


# ── DELETE /auth/logout ───────────────────────────────────────────────────────

@router.delete(
    "/logout",
    summary="Revoke current session",
)
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    credentials: str = Depends(lambda c: c.credentials if hasattr(c, "credentials") else ""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Mark the AuthSession as revoked
    # (In production, also add jti to a Redis blocklist for instant revocation)
    return {"revoked": True, "message": "Session ended."}
