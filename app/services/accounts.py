from dataclasses import dataclass
from datetime import datetime, timezone

from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMember, User


password_hasher = PasswordHash.recommended()


@dataclass
class AuthContext:
    user: User
    household: Household
    membership: HouseholdMember


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalize_email(email)))


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
    if user is None or not user.is_active:
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
) -> AuthContext:
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
    )
    household = Household(name=_build_household_name(session, household_name, display_name))
    session.add_all([user, household])
    session.flush()

    membership = HouseholdMember(household_id=household.id, user_id=user.id, role="owner")
    session.add(membership)
    session.commit()

    return get_auth_context_for_user(session, user.id)


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