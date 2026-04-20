from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.household import Household, HouseholdMember, User


password_hasher = PasswordHash.recommended()


@dataclass
class AuthContext:
    user: User
    household: Household
    membership: HouseholdMember


class TokenStatus(str, Enum):
    INVALID = "invalid"
    EXPIRED = "expired"


@dataclass
class TokenResult:
    user: User | None
    status: TokenStatus | None = None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def _token_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.session_secret)


def _build_user_token(user: User, *, purpose: str) -> str:
    serializer = _token_serializer()
    return serializer.dumps({"user_id": user.id, "email": user.email}, salt=purpose)


def _resolve_user_token(session: Session, token: str, *, purpose: str, max_age_seconds: int) -> TokenResult:
    serializer = _token_serializer()
    try:
        payload = serializer.loads(token, salt=purpose, max_age=max_age_seconds)
    except SignatureExpired:
        return TokenResult(user=None, status=TokenStatus.EXPIRED)
    except BadSignature:
        return TokenResult(user=None, status=TokenStatus.INVALID)

    user = session.get(User, int(payload.get("user_id", 0)))
    if user is None or user.email != payload.get("email"):
        return TokenResult(user=None, status=TokenStatus.INVALID)
    return TokenResult(user=user)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalize_email(email)))


def create_email_verification_token(user: User) -> str:
    return _build_user_token(user, purpose="verify-email")


def create_password_reset_token(user: User) -> str:
    return _build_user_token(user, purpose="password-reset")


def resolve_email_verification_token(session: Session, token: str) -> TokenResult:
    settings = get_settings()
    return _resolve_user_token(
        session,
        token,
        purpose="verify-email",
        max_age_seconds=settings.email_verification_max_age_seconds,
    )


def resolve_password_reset_token(session: Session, token: str) -> TokenResult:
    settings = get_settings()
    return _resolve_user_token(
        session,
        token,
        purpose="password-reset",
        max_age_seconds=settings.password_reset_max_age_seconds,
    )


def get_auth_context_for_user(session: Session, user_id: int) -> AuthContext | None:
    membership = session.scalar(
        select(HouseholdMember)
        .where(HouseholdMember.user_id == user_id)
        .order_by(HouseholdMember.created_at.asc(), HouseholdMember.id.asc())
    )
    if membership is None:
        return None

    user = membership.user
    household = membership.household
    if user is None or household is None:
        return None

    return AuthContext(user=user, household=household, membership=membership)


def authenticate_user(session: Session, email: str, password: str) -> AuthContext | None:
    user = get_user_by_email(session, email)
    if user is None or not user.is_active or user.email_verified_at is None:
        return None
    if not verify_password(password, user.password_hash):
        return None

    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return get_auth_context_for_user(session, user.id)


def _build_household_name(session: Session, requested_name: str, display_name: str) -> str:
    base_name = requested_name.strip() or f"{display_name.strip() or 'Household'} Household"
    candidate = base_name
    suffix = 2

    while session.scalar(select(Household.id).where(func.lower(Household.name) == candidate.lower())) is not None:
        candidate = f"{base_name} {suffix}"
        suffix += 1

    return candidate


def register_owner_account(
    session: Session,
    *,
    email: str,
    display_name: str,
    password: str,
    household_name: str,
) -> User:
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise ValueError("Email is required.")
    if not display_name.strip():
        raise ValueError("Display name is required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if get_user_by_email(session, normalized_email) is not None:
        raise ValueError("An account with that email already exists.")

    user = User(
        email=normalized_email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        is_active=True,
        email_verified_at=None,
    )
    household = Household(name=_build_household_name(session, household_name, display_name))
    session.add_all([user, household])
    session.flush()

    membership = HouseholdMember(household_id=household.id, user_id=user.id, role="owner")
    session.add(membership)
    session.commit()

    session.refresh(user)
    return user


def list_household_members(session: Session, household_id: int) -> list[HouseholdMember]:
    return list(
        session.scalars(
            select(HouseholdMember)
            .where(HouseholdMember.household_id == household_id)
            .order_by(HouseholdMember.role.desc(), HouseholdMember.created_at.asc(), HouseholdMember.id.asc())
        )
    )


def add_household_member(
    session: Session,
    *,
    household_id: int,
    email: str,
    display_name: str,
    password: str,
    role: str,
) -> HouseholdMember:
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise ValueError("Email is required.")

    normalized_role = "owner" if role == "owner" else "member"
    user = get_user_by_email(session, normalized_email)
    if user is None:
        if not display_name.strip():
            raise ValueError("Display name is required for a new account.")
        if len(password) < 8:
            raise ValueError("Temporary password must be at least 8 characters.")

        user = User(
            email=normalized_email,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            is_active=True,
            email_verified_at=None,
        )
        session.add(user)
        session.flush()

    existing_membership = session.scalar(
        select(HouseholdMember).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id == user.id,
        )
    )
    if existing_membership is not None:
        raise ValueError("That user is already in this household.")

    membership = HouseholdMember(household_id=household_id, user_id=user.id, role=normalized_role)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def remove_household_member(session: Session, *, household_id: int, member_id: int, acting_user_id: int) -> None:
    membership = session.scalar(
        select(HouseholdMember).where(
            HouseholdMember.id == member_id,
            HouseholdMember.household_id == household_id,
        )
    )
    if membership is None:
        raise ValueError("Member not found.")
    if membership.user_id == acting_user_id:
        raise ValueError("You cannot remove your own access.")

    if membership.role == "owner":
        owner_count = session.scalar(
            select(func.count(HouseholdMember.id)).where(
                HouseholdMember.household_id == household_id,
                HouseholdMember.role == "owner",
            )
        )
        if (owner_count or 0) <= 1:
            raise ValueError("This household must keep at least one owner.")

    session.delete(membership)
    session.commit()


def mark_email_verified(session: Session, user: User) -> User:
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def update_password(session: Session, user: User, new_password: str) -> User:
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user