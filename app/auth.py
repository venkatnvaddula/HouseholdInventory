from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.services.accounts import AuthContext, get_auth_context_for_user


def get_optional_auth_context(
    request: Request,
    session: Session = Depends(get_db_session),
) -> AuthContext | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None

    context = get_auth_context_for_user(session, int(user_id))
    if context is None or not context.user.is_active:
        request.session.clear()
        return None

    return context


def require_auth_context(
    context: AuthContext | None = Depends(get_optional_auth_context),
) -> AuthContext:
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return context