from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user, log_audit
from app.core.security import hash_token
from app.core.limiter import limiter
from app.database import get_db
from app.models import BrokerConnection, BrokerType, FyersOAuthState, User
from app.brokers.fyers_oauth import FyersOAuth2, FyersOAuthError, FyersTokenStore
from app.schemas.auth import (
    BrokerConnectRequest,
    BrokerConnectionResponse,
    FyersCallbackRequest,
    FyersConnectionStatus,
    FyersLoginResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MFAVerifyRequest,
    MFASetupResponse,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.schemas.profile import LogoutOthersRequest, SessionResponse
from app.services.session_service import session_service
from app.services.auth_service import auth_service, broker_service
from app.services.email_service import email_service


def _unconfigured_smtp_message(action: str, url: str) -> MessageResponse:
    if settings.app_env == "production":
        return MessageResponse(
            message=f"{action} requested. Check your inbox, or contact support if mail is delayed."
        )
    return MessageResponse(message=f"SMTP is not configured. {action} using this link: {url}")


router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_session_cookies(response: Response, access: str, refresh: str) -> None:
    import secrets
    secure = settings.cookie_secure or settings.app_env == "production"
    common = {"secure": secure, "samesite": "strict", "path": "/"}
    response.set_cookie("gnk_access", access, httponly=True, max_age=settings.jwt_access_token_expire_minutes * 60, **common)
    response.set_cookie("gnk_refresh", refresh, httponly=True, max_age=settings.jwt_refresh_token_expire_days * 86400, **common)
    response.set_cookie("gnk_csrf", secrets.token_urlsafe(32), httponly=False, max_age=settings.jwt_refresh_token_expire_days * 86400, **common)


def _clear_session_cookies(response: Response) -> None:
    for name in ("gnk_access", "gnk_refresh", "gnk_csrf"):
        response.delete_cookie(name, path="/")


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def register(data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        user, verify_token = await auth_service.register(db, data, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    verify_url = f"{settings.frontend_url}/verify-email?token={verify_token}"
    if email_service.enabled():
        try:
            await email_service.send_verification(user.email, verify_url)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Account created but email failed to send. Check SMTP settings. {exc}",
            )
        return MessageResponse(message="Registration successful. Check your inbox for the verification link.")

    return _unconfigured_smtp_message("Verify", verify_url)


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("10/minute")
async def resend_verification(
    data: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        verify_token = await auth_service.create_verification_token(db, data.email)
    except ValueError as e:
        # Do not reveal whether the email exists when user is missing
        if "already verified" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        return MessageResponse(message="If the email exists, a verification link has been sent.")

    verify_url = f"{settings.frontend_url}/verify-email?token={verify_token}"
    if email_service.enabled():
        try:
            await email_service.send_verification(data.email, verify_url)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Email failed to send: {exc}")
        return MessageResponse(message="If the email exists, a verification link has been sent.")
    return _unconfigured_smtp_message("Verify", verify_url)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(data: VerifyEmailRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await auth_service.verify_email(db, data.token, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MessageResponse(message="Email verified successfully. You can now login.")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        access, refresh, _ = await auth_service.login(
            db, data.email, data.password, data.mfa_code, request
        )
    except ValueError as e:
        # Rejected logins can intentionally update security state (failed-attempt
        # counters, lockouts, MFA backup-code use, and audit records).  Persist
        # those changes before raising HTTPException, which otherwise causes the
        # request-scoped session dependency to roll the transaction back.
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    _set_session_cookies(response, access, refresh)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(data: RefreshRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = data.refresh_token or request.cookies.get("gnk_refresh")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session missing")
    try:
        access, refresh = await auth_service.refresh_tokens(db, refresh_token, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    _set_session_cookies(response, access, refresh)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("10/minute")
async def forgot_password(
    data: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    token = await auth_service.forgot_password(db, data.email, request)
    if not token:
        return MessageResponse(message="If the email exists, a reset link has been sent.")
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    if email_service.enabled():
        try:
            await email_service.send_password_reset(data.email, reset_url)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Email failed to send: {exc}")
        return MessageResponse(message="If the email exists, a reset link has been sent.")
    return _unconfigured_smtp_message("Reset", reset_url)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        await auth_service.reset_password(db, data.token, data.new_password, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MessageResponse(message="Password reset successful. Please login.")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    request: Request,
    refresh_token: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await session_service.list_sessions(db, current_user, refresh_token or request.cookies.get("gnk_refresh"))
    return sessions


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await session_service.revoke_session(db, current_user, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return MessageResponse(message="Device logged out")


@router.post("/sessions/logout-others", response_model=MessageResponse)
async def logout_other_sessions(
    data: LogoutOthersRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    refresh_token = data.refresh_token or request.cookies.get("gnk_refresh")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Current session missing")
    count = await session_service.logout_others(db, current_user, refresh_token)
    return MessageResponse(message=f"Logged out {count} other device(s).")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: RefreshRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.core.security import hash_token
    from app.models import UserSession

    refresh_token = data.refresh_token or request.cookies.get("gnk_refresh")
    token_hash = hash_token(refresh_token) if refresh_token else ""
    result = await db.execute(select(UserSession).where(UserSession.refresh_token_hash == token_hash))
    session = result.scalar_one_or_none()
    if session:
        session.revoked = True
    _clear_session_cookies(response)
    return MessageResponse(message="Logged out")


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret, qr_uri, backup_codes = await auth_service.setup_mfa(db, current_user)
    return MFASetupResponse(secret=secret, qr_uri=qr_uri, backup_codes=backup_codes)


@router.post("/mfa/enable", response_model=MessageResponse)
async def mfa_enable(
    data: MFAVerifyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await auth_service.enable_mfa(db, current_user, data.code, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MessageResponse(message="MFA enabled successfully.")


brokers_router = APIRouter(prefix="/brokers", tags=["Brokers"])


@brokers_router.get("/fyers/login", response_model=FyersLoginResponse)
async def fyers_login(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    oauth = FyersOAuth2()
    try:
        raw_state = secrets.token_urlsafe(32)
        state = FyersOAuthState(
            user_id=current_user.id,
            state_hash=hash_token(raw_state),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.fyers_oauth_state_ttl_seconds),
        )
        db.add(state)
        await log_audit(db, "broker.oauth.started.fyers", current_user.id, request)
        await db.flush()
        return FyersLoginResponse(
            authorization_url=oauth.get_auth_url(raw_state),
            expires_in=settings.fyers_oauth_state_ttl_seconds,
        )
    except FyersOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@brokers_router.post("/fyers/callback", response_model=BrokerConnectionResponse)
async def fyers_callback(
    data: FyersCallbackRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(FyersOAuthState)
        .where(FyersOAuthState.state_hash == hash_token(data.state), FyersOAuthState.user_id == current_user.id)
        .with_for_update()
    )
    oauth_state = result.scalar_one_or_none()
    expires_at = oauth_state.expires_at.replace(tzinfo=timezone.utc) if oauth_state and oauth_state.expires_at.tzinfo is None else (oauth_state.expires_at if oauth_state else None)
    if not oauth_state or oauth_state.used_at or not expires_at or expires_at <= now:
        raise HTTPException(status_code=400, detail="Invalid or expired FYERS authorization state")
    oauth_state.used_at = now
    oauth = FyersOAuth2()
    try:
        tokens = await oauth.exchange_code_for_token(data.auth_code)
    except FyersOAuthError as exc:
        await log_audit(db, "broker.oauth.failed.fyers", current_user.id, request, {"reason": "upstream_rejected"})
        raise HTTPException(status_code=502, detail="FYERS authorization failed") from exc

    encrypted = FyersTokenStore.store_tokens(tokens["access_token"], tokens["expires_in"], tokens["client_id"])
    existing = await db.execute(select(BrokerConnection).where(
        BrokerConnection.user_id == current_user.id, BrokerConnection.broker == BrokerType.FYERS
    ))
    conn = existing.scalar_one_or_none()
    if conn:
        conn.encrypted_credentials = encrypted
        conn.client_id = tokens["client_id"]
        conn.is_active = True
        conn.health_status = "connected"
        conn.last_health_check = now
    else:
        conn = BrokerConnection(
            user_id=current_user.id, broker=BrokerType.FYERS, encrypted_credentials=encrypted,
            client_id=tokens["client_id"], is_active=True, health_status="connected", last_health_check=now,
        )
        db.add(conn)
    await log_audit(db, "broker.connected.fyers", current_user.id, request, {"oauth": "v3"})
    await db.flush()
    return conn


@brokers_router.get("/fyers/status", response_model=FyersConnectionStatus)
async def fyers_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BrokerConnection).where(
        BrokerConnection.user_id == current_user.id, BrokerConnection.broker == BrokerType.FYERS,
        BrokerConnection.is_active.is_(True),
    ))
    conn = result.scalar_one_or_none()
    if not conn:
        return FyersConnectionStatus(broker="fyers", status="disconnected", health_status="not_connected")
    return FyersConnectionStatus(
        broker="fyers", status="connected" if conn.health_status == "connected" else "error",
        client_id=conn.client_id, health_status=conn.health_status, last_health_check=conn.last_health_check,
    )


@brokers_router.delete("/fyers/connection", response_model=MessageResponse)
async def disconnect_fyers(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BrokerConnection).where(
        BrokerConnection.user_id == current_user.id, BrokerConnection.broker == BrokerType.FYERS
    ))
    conn = result.scalar_one_or_none()
    if conn:
        await db.delete(conn)
        await log_audit(db, "broker.disconnected.fyers", current_user.id, request)
    return MessageResponse(message="FYERS connection disconnected")


@brokers_router.post("/connect", response_model=BrokerConnectionResponse)
async def connect_broker(
    data: BrokerConnectRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    credentials = {}
    if data.api_key:
        credentials["api_key"] = data.api_key
    if data.api_secret:
        credentials["api_secret"] = data.api_secret
    if data.access_token:
        credentials["access_token"] = data.access_token
    if data.client_id:
        credentials["client_id"] = data.client_id

    if not credentials:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No credentials provided")

    try:
        conn = await broker_service.connect(db, current_user, data.broker, credentials, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return conn


@brokers_router.get("/connections", response_model=list[BrokerConnectionResponse])
async def list_broker_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connections = await broker_service.list_connections(db, current_user)
    return connections
