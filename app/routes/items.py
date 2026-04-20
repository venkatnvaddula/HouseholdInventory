import csv
from datetime import date
from io import StringIO
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.services.items import (
    CATEGORY_OPTIONS,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_DIR,
    LOCATION_OPTIONS,
    SORTABLE_COLUMNS,
    bulk_delete_items,
    bulk_update_items,
    create_item,
    delete_item,
    get_item,
    list_item_history,
    list_item_names,
    list_items,
    normalize_choice,
    update_item,
)


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter(tags=["items"])


BULK_EDIT_FIELDS = {
    "name": "Name",
    "category": "Category",
    "count": "Count",
    "size": "Size",
    "units": "Units",
    "location": "Location",
    "price": "Price",
    "purchase_date": "Purchase date",
    "expiry_date": "Expiry date",
    "notes": "Notes",
}


def _sanitize_sort(sort_by: str, sort_dir: str) -> tuple[str, str]:
    safe_sort_by = sort_by if sort_by in SORTABLE_COLUMNS else DEFAULT_SORT_BY
    safe_sort_dir = sort_dir if sort_dir in {"asc", "desc"} else DEFAULT_SORT_DIR
    return safe_sort_by, safe_sort_dir


def _next_sort_dir(current_sort_by: str, current_sort_dir: str, column: str) -> str:
    if current_sort_by == column and current_sort_dir == "asc":
        return "desc"
    return "asc"


def _table_context(
    request: Request,
    items,
    *,
    search: str,
    sort_by: str,
    sort_dir: str,
) -> dict[str, object]:
    return {
        "bulk_edit_fields": BULK_EDIT_FIELDS,
        "category_options": CATEGORY_OPTIONS,
        "items": items,
        "location_options": LOCATION_OPTIONS,
        "request": request,
        "search": search,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "sortable_columns": [
            {
                "key": "name",
                "label": "Name",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "name"),
            },
            {
                "key": "category",
                "label": "Category",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "category"),
            },
            {
                "key": "count",
                "label": "Count",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "count"),
            },
            {
                "key": "size",
                "label": "Size",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "size"),
            },
            {
                "key": "units",
                "label": "Units",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "units"),
            },
            {
                "key": "location",
                "label": "Location",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "location"),
            },
            {
                "key": "purchase_date",
                "label": "Purchased",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "purchase_date"),
            },
            {
                "key": "expiry_date",
                "label": "Expires",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "expiry_date"),
            },
            {
                "key": "price",
                "label": "Price",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "price"),
            },
            {
                "key": "notes",
                "label": "Notes",
                "next_dir": _next_sort_dir(sort_by, sort_dir, "notes"),
            },
        ],
    }


def _item_form_context(session: Session, item) -> dict[str, object]:
    item_names = list_item_names(session)
    today_value = date.today().isoformat()

    category_value = item.category if item else "Food"
    location_value = item.location if item else "Pantry"

    return {
        "category_custom": category_value if category_value not in CATEGORY_OPTIONS else "",
        "category_options": CATEGORY_OPTIONS,
        "category_value": category_value if category_value in CATEGORY_OPTIONS else "__custom__",
        "item": item,
        "item_names": item_names,
        "location_custom": location_value if location_value not in LOCATION_OPTIONS else "",
        "location_options": LOCATION_OPTIONS,
        "location_value": location_value if location_value in LOCATION_OPTIONS else "__custom__",
        "today_value": today_value,
    }


def _render_item_table(
    request: Request,
    session: Session,
    sort_by: str,
    sort_dir: str,
    search: str,
) -> HTMLResponse:
    sort_by, sort_dir = _sanitize_sort(sort_by, sort_dir)
    try:
        items = list_items(
            session,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
        )
    except ProgrammingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready. Run the local database and migrations first.",
        ) from exc

    return templates.TemplateResponse(
        request,
        "items/table.html",
        _table_context(
            request,
            items,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
        ),
    )


def _csv_export_response(
    session: Session,
    sort_by: str,
    sort_dir: str,
    search: str,
) -> StreamingResponse:
    sort_by, sort_dir = _sanitize_sort(sort_by, sort_dir)
    try:
        items = list_items(
            session,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
        )
    except ProgrammingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready. Run the local database and migrations first.",
        ) from exc

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "name",
        "category",
        "count",
        "size",
        "units",
        "location",
        "price",
        "purchase_date",
        "expiry_date",
        "notes",
    ])

    for item in items:
        writer.writerow([
            item.id,
            item.name,
            item.category,
            item.count,
            f"{item.size:g}",
            item.units,
            item.location,
            f"{item.price:.2f}" if item.price is not None else "",
            item.purchase_date.isoformat() if item.purchase_date else "",
            item.expiry_date.isoformat() if item.expiry_date else "",
            item.notes or "",
        ])

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="all-items.csv"'},
    )


def _history_csv_export_response(session: Session) -> StreamingResponse:
    try:
        items = list_item_history(session)
    except ProgrammingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready. Run the local database and migrations first.",
        ) from exc

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "name",
        "category",
        "count",
        "size",
        "units",
        "location",
        "price",
        "purchase_date",
        "expiry_date",
        "notes",
        "created_at",
        "updated_at",
        "deleted_at",
    ])

    for item in items:
        writer.writerow([
            item.id,
            item.name,
            item.category,
            item.count,
            f"{item.size:g}",
            item.units,
            item.location,
            f"{item.price:.2f}" if item.price is not None else "",
            item.purchase_date.isoformat() if item.purchase_date else "",
            item.expiry_date.isoformat() if item.expiry_date else "",
            item.notes or "",
            item.created_at.isoformat() if item.created_at else "",
            item.updated_at.isoformat() if item.updated_at else "",
            item.deleted_at.isoformat() if item.deleted_at else "",
        ])

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventory-history.csv"'},
    )


@router.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    return RedirectResponse(url="/items", status_code=status.HTTP_302_FOUND)


@router.get("/items", response_class=HTMLResponse)
def items_page(
    request: Request,
    search: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    sort_by, sort_dir = _sanitize_sort(sort_by, sort_dir)
    try:
        items = list_items(
            session,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
        )
    except ProgrammingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready. Run the local database and migrations first.",
        ) from exc

    return templates.TemplateResponse(
        request,
        "items/list.html",
        _table_context(
            request,
            items,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
        ),
    )


@router.get("/items/table", response_class=HTMLResponse)
def items_table(
    request: Request,
    search: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    return _render_item_table(request, session, sort_by, sort_dir, search)


@router.get("/items/export.csv")
def export_items_csv(
    search: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    session: Session = Depends(get_db_session),
) -> StreamingResponse:
    return _csv_export_response(session, sort_by, sort_dir, search)


@router.get("/items/export-history.csv")
def export_items_history_csv(
    session: Session = Depends(get_db_session),
) -> StreamingResponse:
    return _history_csv_export_response(session)


@router.post("/items/bulk-update")
def bulk_update_items_action(
    item_ids: list[int] = Form(default=[]),
    field: str = Form(...),
    text_value: str = Form(""),
    number_value: float | None = Form(None),
    date_value: date | None = Form(None),
    category_choice: str = Form("Food"),
    category_custom: str = Form(""),
    location_choice: str = Form("Pantry"),
    location_custom: str = Form(""),
    search: str = Form(""),
    sort_by: str = Form(DEFAULT_SORT_BY),
    sort_dir: str = Form(DEFAULT_SORT_DIR),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    sort_by, sort_dir = _sanitize_sort(sort_by, sort_dir)

    bulk_value: str | float | date | None = text_value
    if field == "category":
        bulk_value = normalize_choice(category_choice, category_custom, "Food")
    elif field == "location":
        bulk_value = normalize_choice(location_choice, location_custom, "Pantry")
    elif field in {"count", "size", "price"}:
        bulk_value = number_value
    elif field in {"purchase_date", "expiry_date"}:
        bulk_value = date_value

    bulk_update_items(session, item_ids=item_ids, field=field, value=bulk_value)

    target = f"/items?search={search}&sort_by={sort_by}&sort_dir={sort_dir}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/bulk-delete")
def bulk_delete_items_action(
    item_ids: list[int] = Form(default=[]),
    search: str = Form(""),
    sort_by: str = Form(DEFAULT_SORT_BY),
    sort_dir: str = Form(DEFAULT_SORT_DIR),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    sort_by, sort_dir = _sanitize_sort(sort_by, sort_dir)
    bulk_delete_items(session, item_ids=item_ids)

    target = f"/items?search={search}&sort_by={sort_by}&sort_dir={sort_dir}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/items/new", response_class=HTMLResponse)
def new_item_page(request: Request, session: Session = Depends(get_db_session)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "form_action": "/items",
            "page_title": "Add item",
            "request": request,
            **_item_form_context(session, None),
        },
    )


@router.post("/items")
def create_item_action(
    name: str = Form(...),
    category: str = Form("Food"),
    category_custom: str = Form(""),
    count: int = Form(1),
    size: float = Form(1.0),
    units: str = Form("item"),
    location: str = Form("Pantry"),
    location_custom: str = Form(""),
    price: str = Form(""),
    purchase_date: date = Form(default_factory=date.today),
    expiry_date: date | None = Form(None),
    notes: str = Form(""),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    category_value = normalize_choice(category, category_custom, "Food")
    location_value = normalize_choice(location, location_custom, "Pantry")
    create_item(
        session,
        name=name,
        category=category_value,
        count=count,
        size=size,
        units=units,
        location=location_value,
        price=price,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        notes=notes,
    )
    return RedirectResponse(url="/items", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item_page(
    item_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    item = get_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "form_action": f"/items/{item_id}",
            "page_title": "Edit item",
            "request": request,
            **_item_form_context(session, item),
        },
    )


@router.post("/items/{item_id}")
def update_item_action(
    item_id: int,
    name: str = Form(...),
    category: str = Form("Food"),
    category_custom: str = Form(""),
    count: int = Form(1),
    size: float = Form(1.0),
    units: str = Form("item"),
    location: str = Form("Pantry"),
    location_custom: str = Form(""),
    price: str = Form(""),
    purchase_date: date = Form(default_factory=date.today),
    expiry_date: date | None = Form(None),
    notes: str = Form(""),
    search: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    sort_by, sort_dir = _sanitize_sort(sort_by, sort_dir)
    item = get_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    category_value = normalize_choice(category, category_custom, "Food")
    location_value = normalize_choice(location, location_custom, "Pantry")

    update_item(
        session,
        item,
        name=name,
        category=category_value,
        count=count,
        size=size,
        units=units,
        location=location_value,
        price=price,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        notes=notes,
    )
    target = f"/items?search={search}&sort_by={sort_by}&sort_dir={sort_dir}"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/items/{item_id}", response_class=HTMLResponse)
def delete_item_action(
    item_id: int,
    request: Request,
    search: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    delete_item(session, item_id)
    return _render_item_table(request, session, sort_by, sort_dir, search)