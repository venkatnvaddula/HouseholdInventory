from pathlib import Path

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
    list_household_members,
    register_owner_account,
    remove_household_member,
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
        auth_context = register_owner_account(
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

    request.session["user_id"] = auth_context.user.id
    return RedirectResponse(url="/items", status_code=status.HTTP_303_SEE_OTHER)


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