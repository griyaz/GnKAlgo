import json
import hmac
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import log_audit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_data,
    encrypt_data,
    generate_secure_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.models import (
    BrokerConnection,
    BrokerType,
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserSession,
)
from app.schemas.auth import RegisterRequest


class AuthService:
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    async def register(self, db: AsyncSession, data: RegisterRequest, request: Request) -> tuple[User, str]:
        existing = await db.execute(select(User).where(User.email == data.email.lower()))
        if existing.scalar_one_or_none():
            raise ValueError("Email already registered")

        if data.phone:
            phone_check = await db.execute(select(User).where(User.phone == data.phone))
            if phone_check.scalar_one_or_none():
                raise ValueError("Phone number already registered")

        user = User(
            email=data.email.lower(),
            phone=data.phone,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            gender=data.gender,
            date_of_birth=data.date_of_birth,
        )
        db.add(user)
        await db.flush()

        raw_token = generate_secure_token()
        verification = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(verification)
        await log_audit(db, "user.registered", user.id, request)
        return user, raw_token

    async def create_verification_token(self, db: AsyncSession, email: str) -> str:
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("If the email exists, a verification link has been sent.")
        if user.is_verified:
            raise ValueError("Email is already verified. You can login.")
        raw_token = generate_secure_token()
        verification = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(verification)
        return raw_token

    async def verify_email(self, db: AsyncSession, raw_token: str, request: Request) -> User:
        token_hash = hash_token(raw_token)
        result = await db.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.used == False,
                EmailVerificationToken.expires_at > datetime.now(timezone.utc),
            )
        )
        token_row = result.scalar_one_or_none()
        if not token_row:
            raise ValueError("Invalid or expired verification token")

        user_result = await db.execute(select(User).where(User.id == token_row.user_id))
        user = user_result.scalar_one()
        user.is_verified = True
        token_row.used = True
        await log_audit(db, "user.email_verified", user.id, request)
        return user

    async def login(
        self, db: AsyncSession, email: str, password: str, mfa_code: str | None, request: Request
    ) -> tuple[str, str, User]:
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("Invalid email or password")

        if not user.is_active:
            raise ValueError("Account is disabled")

        locked_until = user.locked_until
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until and locked_until > datetime.now(timezone.utc):
            raise ValueError("Account temporarily locked. Try again later.")

        if not verify_password(password, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=self.LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
            await log_audit(db, "user.login_failed", user.id, request)
            raise ValueError("Invalid email or password")

        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        verification_required = (
            settings.app_env == "production" or settings.email_verification_required
        )
        if not user.is_verified and verification_required:
            raise ValueError("Please verify your email before logging in")

        if user.mfa_enabled:
            if not mfa_code:
                raise ValueError("MFA code required")
            if not self._verify_mfa(user, mfa_code):
                await log_audit(db, "user.mfa_failed", user.id, request)
                raise ValueError("Invalid MFA code")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(timezone.utc)
        if user.email.lower() in settings.admin_email_list:
            user.is_admin = True

        refresh, expires = create_refresh_token(str(user.id))

        session = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            expires_at=expires,
            last_active_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()
        access = create_access_token(str(user.id), extra={"sid": str(session.id)})
        await log_audit(db, "user.login_success", user.id, request)
        return access, refresh, user

    async def refresh_tokens(
        self, db: AsyncSession, refresh_token: str, request: Request
    ) -> tuple[str, str]:
        from app.core.security import decode_token

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise ValueError("Invalid refresh token")

        token_hash = hash_token(refresh_token)
        result = await db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.revoked == False,
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError("Invalid or expired refresh token")

        session.revoked = True
        user_id = payload["sub"]
        new_refresh, expires = create_refresh_token(user_id)

        new_session = UserSession(
            user_id=uuid.UUID(user_id),
            refresh_token_hash=hash_token(new_refresh),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            expires_at=expires,
            last_active_at=datetime.now(timezone.utc),
        )
        db.add(new_session)
        await db.flush()
        access = create_access_token(user_id, extra={"sid": str(new_session.id)})
        await log_audit(db, "user.token_refreshed", uuid.UUID(user_id), request)
        return access, new_refresh

    def _plain_mfa_secret(self, user: User) -> str | None:
        if not user.mfa_secret:
            return None
        try:
            return decrypt_data(user.mfa_secret)
        except Exception:
            return user.mfa_secret

    def _verify_mfa(self, user: User, code: str) -> bool:
        secret = self._plain_mfa_secret(user)
        if secret:
            totp = pyotp.TOTP(secret)
            if totp.verify(code.strip(), valid_window=1):
                return True
        if not user.mfa_backup_hashes:
            return False
        hashes: list[str] = json.loads(user.mfa_backup_hashes)
        candidate = hash_token(code.strip())
        remaining: list[str] = []
        matched = False
        for stored in hashes:
            if not matched and hmac.compare_digest(candidate, stored):
                matched = True
                continue
            remaining.append(stored)
        if matched:
            user.mfa_backup_hashes = json.dumps(remaining)
        return matched

    async def setup_mfa(self, db: AsyncSession, user: User) -> tuple[str, str, list[str]]:
        secret = pyotp.random_base32()
        user.mfa_secret = encrypt_data(secret)
        totp = pyotp.TOTP(secret)
        qr_uri = totp.provisioning_uri(name=user.email, issuer_name="GnKAlgo")
        backup_codes = [generate_secure_token()[:8].upper() for _ in range(5)]
        user.mfa_backup_hashes = json.dumps([hash_token(c) for c in backup_codes])
        user.mfa_enabled = False
        return secret, qr_uri, backup_codes

    async def enable_mfa(self, db: AsyncSession, user: User, code: str, request: Request) -> None:
        secret = self._plain_mfa_secret(user)
        if not secret:
            raise ValueError("MFA not initialized. Call setup first.")
        totp = pyotp.TOTP(secret)
        if not totp.verify(code.strip(), valid_window=1):
            raise ValueError("Invalid MFA code")
        user.mfa_enabled = True
        await log_audit(db, "user.mfa_enabled", user.id, request)

    async def forgot_password(self, db: AsyncSession, email: str, request: Request) -> str | None:
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if not user:
            return None

        raw_token = generate_secure_token()
        reset = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(reset)
        await log_audit(db, "user.password_reset_requested", user.id, request)
        return raw_token

    async def reset_password(self, db: AsyncSession, raw_token: str, new_password: str, request: Request) -> None:
        token_hash = hash_token(raw_token)
        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used == False,
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
            )
        )
        token_row = result.scalar_one_or_none()
        if not token_row:
            raise ValueError("Invalid or expired reset token")

        user_result = await db.execute(select(User).where(User.id == token_row.user_id))
        user = user_result.scalar_one()
        user.password_hash = hash_password(new_password)
        token_row.used = True

        sessions = await db.execute(select(UserSession).where(UserSession.user_id == user.id))
        for session in sessions.scalars():
            session.revoked = True

        await log_audit(db, "user.password_reset", user.id, request)


class BrokerService:
    @staticmethod
    def _validate_credentials(broker: BrokerType, credentials: dict) -> None:
        token = str(credentials.get("access_token") or credentials.get("api_key") or "").strip()
        if not token:
            raise ValueError("Broker access token is required")
        if broker in {BrokerType.DHAN, BrokerType.FYERS} and not str(
            credentials.get("client_id") or ""
        ).strip():
            raise ValueError(f"{broker.value.upper()} client ID is required")
        if broker is BrokerType.FYERS and not settings.fyers_api_base_url.startswith("https://"):
            raise ValueError("FYERS API base URL must use HTTPS")
        if broker is BrokerType.UPSTOX and not settings.upstox_api_base_url.startswith("https://"):
            raise ValueError("Upstox API base URL must use HTTPS")
        if broker is BrokerType.DHAN and not settings.dhan_api_base_url.startswith("https://"):
            raise ValueError("Dhan API base URL must use HTTPS")

    async def connect(
        self,
        db: AsyncSession,
        user: User,
        broker: str,
        credentials: dict,
        request: Request,
    ) -> BrokerConnection:
        broker_enum = BrokerType(broker)
        self._validate_credentials(broker_enum, credentials)
        token = credentials.get("access_token") or credentials.get("api_key") or ""
        if broker_enum == BrokerType.DHAN:
            from app.brokers.dhan import DhanAdapter

            adapter = DhanAdapter(access_token=token, client_id=credentials.get("client_id"))
        elif broker_enum == BrokerType.FYERS:
            from app.brokers.fyers import FyersExecutionAdapter

            adapter = FyersExecutionAdapter(
                access_token=token, client_id=credentials.get("client_id")
            )
        elif broker_enum == BrokerType.UPSTOX:
            from app.brokers.upstox import UpstoxExecutionAdapter

            adapter = UpstoxExecutionAdapter(access_token=token)
        else:
            from app.brokers.groww import GrowwAdapter

            adapter = GrowwAdapter(access_token=token)
        try:
            await adapter.authenticate(credentials)
            health = "connected"
        except Exception as exc:
            raise ValueError(f"Broker credentials rejected: {exc}") from exc

        creds_json = json.dumps(credentials)
        encrypted = encrypt_data(creds_json)

        existing = await db.execute(
            select(BrokerConnection).where(
                BrokerConnection.user_id == user.id,
                BrokerConnection.broker == broker_enum,
            )
        )
        conn = existing.scalar_one_or_none()
        if conn:
            conn.encrypted_credentials = encrypted
            conn.client_id = credentials.get("client_id") or conn.client_id
            conn.is_active = True
            conn.health_status = health
            conn.last_health_check = datetime.now(timezone.utc)
        else:
            conn = BrokerConnection(
                user_id=user.id,
                broker=broker_enum,
                encrypted_credentials=encrypted,
                client_id=credentials.get("client_id"),
                health_status=health,
                last_health_check=datetime.now(timezone.utc),
            )
            db.add(conn)

        await log_audit(db, f"broker.connected.{broker}", user.id, request)
        await db.flush()
        return conn

    async def list_connections(self, db: AsyncSession, user: User) -> list[BrokerConnection]:
        result = await db.execute(
            select(BrokerConnection).where(BrokerConnection.user_id == user.id)
        )
        return list(result.scalars().all())


auth_service = AuthService()
broker_service = BrokerService()
