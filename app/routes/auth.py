from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_optional_auth_context, require_auth_context
from app.db import get_db_session
from app.services.accounts import (
    AuthContext,
    add_household_member,
    authenticate_user,
    create_email_verification_token,
    create_password_reset_token,
    get_user_by_email,
    list_household_members,
    mark_email_verified,
    register_owner_account,
    remove_household_member,
    resolve_email_verification_token,
    resolve_password_reset_token,
    update_password,
)


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter(tags=["auth"])


def _redirect_authenticated(context: AuthContext | None) -> RedirectResponse | None:
    if context is None:
        return None
    return RedirectResponse(url="/items", status_code=status.HTTP_303_SEE_OTHER)


def _auth_page_context(request: Request, *, page_title: str, error_message: str = "") -> dict[str, object]:
    return {
        "error_message": error_message,
        "page_title": page_title,
        "request": request,
    }


def _build_absolute_path(request: Request, path: str, **query_params: str) -> str:
    query = urlencode(query_params)
    base = str(request.base_url).rstrip("/")
    if query:
        return f"{base}{path}?{query}"
    return f"{base}{path}"


def _token_preview_context(
    request: Request,
    *,
    page_title: str,
    message: str,
    preview_url: str | None = None,
) -> dict[str, object]:
    return {
        "message": message,
        "page_title": page_title,
        "preview_url": preview_url if request.app.state.settings.app_env == "development" else None,
        "request": request,
    }


def _members_page_context(
    request: Request,
    auth_context: AuthContext,
    session: Session,
    *,
    error_message: str = "",
) -> dict[str, object]:
    return {
        "current_household": auth_context.household,
        "current_user": auth_context.user,
        "error_message": error_message,
        "members": list_household_members(session, auth_context.household.id),
        "request": request,
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    auth_context: AuthContext | None = Depends(get_optional_auth_context),
) -> HTMLResponse:
    redirect = _redirect_authenticated(auth_context)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(request, "auth/login.html", _auth_page_context(request, page_title="Log in"))


@router.post("/login", response_class=HTMLResponse)
def login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    user = get_user_by_email(session, email)
    if user is not None and user.email_verified_at is None:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            _auth_page_context(
                request,
                page_title="Log in",
                error_message="Verify your email before logging in. You can request a new verification link below.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    auth_context = authenticate_user(session, email, password)
    if auth_context is None:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            _auth_page_context(request, page_title="Log in", error_message="Invalid email or password."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    request.session["user_id"] = auth_context.user.id
    return RedirectResponse(url="/items", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    auth_context: AuthContext | None = Depends(get_optional_auth_context),
) -> HTMLResponse:
    redirect = _redirect_authenticated(auth_context)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(request, "auth/register.html", _auth_page_context(request, page_title="Create account"))


@router.post("/register", response_class=HTMLResponse)
def register_action(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    household_name: str = Form(""),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    try:
        user = register_owner_account(
            session,
            email=email,
            display_name=display_name,
            password=password,
            household_name=household_name,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            _auth_page_context(request, page_title="Create account", error_message=str(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    verification_token = create_email_verification_token(user)
    verification_url = _build_absolute_path(request, "/verify-email", token=verification_token)
    return templates.TemplateResponse(
        request,
        "auth/token_notice.html",
        _token_preview_context(
            request,
            page_title="Verify your email",
            message="Your account was created. Verify your email before logging in.",
            preview_url=verification_url,
        ),
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/verify-email/request", response_class=HTMLResponse)
def verify_email_request_page(
    request: Request,
    auth_context: AuthContext | None = Depends(get_optional_auth_context),
) -> HTMLResponse:
    redirect = _redirect_authenticated(auth_context)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        request,
        "auth/token_request.html",
        {
            "description": "Enter your email to generate a verification link.",
            "form_action": "/verify-email/request",
            "page_title": "Request verification email",
            "request": request,
            "submit_label": "Send verification link",
        },
    )


@router.post("/verify-email/request", response_class=HTMLResponse)
def verify_email_request_action(
    request: Request,
    email: str = Form(...),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    preview_url = None
    user = get_user_by_email(session, email)
    if user is not None and user.email_verified_at is None:
        preview_url = _build_absolute_path(request, "/verify-email", token=create_email_verification_token(user))

    return templates.TemplateResponse(
        request,
        "auth/token_notice.html",
        _token_preview_context(
            request,
            page_title="Verification link generated",
            message="If that account exists and still needs verification, a verification link has been prepared.",
            preview_url=preview_url,
        ),
    )


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email_action(
    request: Request,
    token: str,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    token_result = resolve_email_verification_token(session, token)
    if token_result.user is None:
        message = "This verification link is invalid or has expired. Request a new one from the verification page."
        if token_result.status and token_result.status.value == "expired":
            message = "This verification link has expired. Request a new verification link and try again."
        return templates.TemplateResponse(
            request,
            "auth/token_result.html",
            {"message": message, "page_title": "Verification failed", "request": request},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    mark_email_verified(session, token_result.user)
    return templates.TemplateResponse(
        request,
        "auth/token_result.html",
        {
            "message": "Your email has been verified. You can log in now.",
            "next_href": "/login",
            "next_label": "Go to login",
            "page_title": "Email verified",
            "request": request,
        },
    )


@router.get("/password-reset/request", response_class=HTMLResponse)
def password_reset_request_page(
    request: Request,
    auth_context: AuthContext | None = Depends(get_optional_auth_context),
) -> HTMLResponse:
    redirect = _redirect_authenticated(auth_context)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        request,
        "auth/token_request.html",
        {
            "description": "Enter your email to generate a password reset link.",
            "form_action": "/password-reset/request",
            "page_title": "Request password reset",
            "request": request,
            "submit_label": "Send reset link",
        },
    )


@router.post("/password-reset/request", response_class=HTMLResponse)
def password_reset_request_action(
    request: Request,
    email: str = Form(...),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    preview_url = None
    user = get_user_by_email(session, email)
    if user is not None:
        preview_url = _build_absolute_path(request, "/password-reset", token=create_password_reset_token(user))

    return templates.TemplateResponse(
        request,
        "auth/token_notice.html",
        _token_preview_context(
            request,
            page_title="Password reset link generated",
            message="If that account exists, a password reset link has been prepared.",
            preview_url=preview_url,
        ),
    )


@router.get("/password-reset", response_class=HTMLResponse)
def password_reset_page(
    request: Request,
    token: str,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    token_result = resolve_password_reset_token(session, token)
    if token_result.user is None:
        message = "This password reset link is invalid or has expired. Request a new one and try again."
        if token_result.status and token_result.status.value == "expired":
            message = "This password reset link has expired. Request a new one and try again."
        return templates.TemplateResponse(
            request,
            "auth/token_result.html",
            {"message": message, "page_title": "Reset link invalid", "request": request},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return templates.TemplateResponse(
        request,
        "auth/password_reset_form.html",
        {"page_title": "Reset password", "request": request, "token": token},
    )


@router.post("/password-reset", response_class=HTMLResponse)
def password_reset_action(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    if password != confirm_password:
        return templates.TemplateResponse(
            request,
            "auth/password_reset_form.html",
            {
                "error_message": "Passwords do not match.",
                "page_title": "Reset password",
                "request": request,
                "token": token,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    token_result = resolve_password_reset_token(session, token)
    if token_result.user is None:
        return templates.TemplateResponse(
            request,
            "auth/token_result.html",
            {
                "message": "This password reset link is invalid or has expired. Request a new one and try again.",
                "page_title": "Reset failed",
                "request": request,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        update_password(session, token_result.user, password)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "auth/password_reset_form.html",
            {
                "error_message": str(exc),
                "page_title": "Reset password",
                "request": request,
                "token": token,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return templates.TemplateResponse(
        request,
        "auth/token_result.html",
        {
            "message": "Your password has been updated. You can log in with the new password now.",
            "next_href": "/login",
            "next_label": "Go to login",
            "page_title": "Password updated",
            "request": request,
        },
    )


@router.post("/logout")
def logout_action(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/household/members", response_class=HTMLResponse)
def household_members_page(
    request: Request,
    auth_context: AuthContext = Depends(require_auth_context),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "household/members.html",
        _members_page_context(request, auth_context, session),
    )


@router.post("/household/members", response_class=HTMLResponse)
def add_household_member_action(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(""),
    password: str = Form(""),
    role: str = Form("member"),
    auth_context: AuthContext = Depends(require_auth_context),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    if auth_context.membership.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can manage household members.")

    try:
        add_household_member(
            session,
            household_id=auth_context.household.id,
            email=email,
            display_name=display_name,
            password=password,
            role=role,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "household/members.html",
            _members_page_context(request, auth_context, session, error_message=str(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/household/members", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/household/members/{member_id}/remove", response_class=HTMLResponse)
def remove_household_member_action(
    member_id: int,
    request: Request,
    auth_context: AuthContext = Depends(require_auth_context),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    if auth_context.membership.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can manage household members.")

    try:
        remove_household_member(
            session,
            household_id=auth_context.household.id,
            member_id=member_id,
            acting_user_id=auth_context.user.id,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "household/members.html",
            _members_page_context(request, auth_context, session, error_message=str(exc)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/household/members", status_code=status.HTTP_303_SEE_OTHER)