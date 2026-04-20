from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Select, delete, distinct, func, select
from sqlalchemy.orm import Session

from app.models.item import Item


DEFAULT_HOUSEHOLD_ID = 1
CATEGORY_OPTIONS = ["Food", "Personal Care", "Household"]
LOCATION_OPTIONS = [
    "Fridge",
    "Pantry",
    "Bathroom",
    "Storage",
    "Bedroom Closet",
    "Kitchen",
    "Bedroom",
    "Living Room",
    "Outdoor Storage",
]
SORTABLE_COLUMNS = {
    "name": Item.name,
    "category": Item.category,
    "count": Item.count,
    "size": Item.size,
    "units": Item.units,
    "location": Item.location,
    "purchase_date": Item.purchase_date,
    "expiry_date": Item.expiry_date,
    "price": Item.price,
    "notes": Item.notes,
}
DEFAULT_SORT_BY = "expiry_date"
DEFAULT_SORT_DIR = "asc"


def build_items_query(
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    search: str = "",
) -> Select[tuple[Item]]:
    statement = select(Item).where(
        Item.household_id == DEFAULT_HOUSEHOLD_ID,
        Item.deleted_at.is_(None),
    )

    search = search.strip()
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            Item.name.ilike(pattern)
            | Item.category.ilike(pattern)
            | Item.location.ilike(pattern)
            | Item.units.ilike(pattern)
            | Item.notes.ilike(pattern)
        )

    sort_column = SORTABLE_COLUMNS.get(sort_by, SORTABLE_COLUMNS[DEFAULT_SORT_BY])
    if sort_by in {"name", "category", "units", "location", "notes"}:
        normalized_column = func.lower(func.coalesce(sort_column, ""))
        sort_expression = normalized_column.desc() if sort_dir == "desc" else normalized_column.asc()
        return statement.order_by(sort_expression, Item.name.asc())

    sort_expression = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
    if sort_by in {"purchase_date", "expiry_date", "price"}:
        return statement.order_by(sort_column.is_(None), sort_expression, Item.name.asc())
    return statement.order_by(sort_expression, Item.name.asc())


def list_items(
    session: Session,
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    search: str = "",
) -> list[Item]:
    return list(
        session.scalars(
            build_items_query(sort_by=sort_by, sort_dir=sort_dir, search=search)
        )
    )


def list_item_names(session: Session) -> list[str]:
    statement = (
        select(distinct(Item.name))
        .where(Item.household_id == DEFAULT_HOUSEHOLD_ID)
        .order_by(Item.name.asc())
    )
    return [name for name in session.scalars(statement) if name]


def list_item_history(session: Session) -> list[Item]:
    statement = (
        select(Item)
        .where(Item.household_id == DEFAULT_HOUSEHOLD_ID)
        .order_by(Item.created_at.desc(), Item.id.desc())
    )
    return list(session.scalars(statement))


def normalize_choice(selected_value: str, custom_value: str, fallback: str) -> str:
    custom_value = custom_value.strip()
    if selected_value == "__custom__":
        return custom_value or fallback
    return selected_value.strip() or fallback


def get_item(session: Session, item_id: int) -> Item | None:
    statement = select(Item).where(
        Item.id == item_id,
        Item.household_id == DEFAULT_HOUSEHOLD_ID,
        Item.deleted_at.is_(None),
    )
    return session.scalar(statement)


def create_item(
    session: Session,
    *,
    name: str,
    category: str,
    count: int,
    size: float,
    units: str,
    location: str,
    price: str,
    purchase_date: date | None,
    expiry_date: date | None,
    notes: str,
) -> Item:
    item = Item(
        household_id=DEFAULT_HOUSEHOLD_ID,
        name=name.strip(),
        category=category,
        count=count,
        size=size,
        units=units.strip() or "item",
        location=location,
        price=Decimal(price) if price else None,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        notes=notes or None,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def update_item(
    session: Session,
    item: Item,
    *,
    name: str,
    category: str,
    count: int,
    size: float,
    units: str,
    location: str,
    price: str,
    purchase_date: date | None,
    expiry_date: date | None,
    notes: str,
) -> Item:
    item.name = name.strip()
    item.category = category
    item.count = count
    item.size = size
    item.units = units.strip() or "item"
    item.location = location
    item.price = Decimal(price) if price else None
    item.purchase_date = purchase_date
    item.expiry_date = expiry_date
    item.notes = notes or None
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete_item(session: Session, item_id: int) -> None:
    item = session.scalar(
        select(Item).where(
            Item.id == item_id,
            Item.household_id == DEFAULT_HOUSEHOLD_ID,
            Item.deleted_at.is_(None),
        )
    )
    if item is None:
        return

    item.deleted_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()


def bulk_delete_items(session: Session, *, item_ids: list[int]) -> None:
    if not item_ids:
        return

    deleted_at = datetime.now(timezone.utc)
    items = list(
        session.scalars(
            select(Item).where(
                Item.household_id == DEFAULT_HOUSEHOLD_ID,
                Item.id.in_(item_ids),
                Item.deleted_at.is_(None),
            )
        )
    )

    for item in items:
        item.deleted_at = deleted_at
        session.add(item)
    session.commit()


def bulk_update_items(
    session: Session,
    *,
    item_ids: list[int],
    field: str,
    value: str | float | date | None,
) -> None:
    allowed_fields = {
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
    }
    if field not in allowed_fields or not item_ids:
        return

    items = list(
        session.scalars(
            select(Item).where(
                Item.household_id == DEFAULT_HOUSEHOLD_ID,
                Item.id.in_(item_ids),
                Item.deleted_at.is_(None),
            )
        )
    )

    for item in items:
        if field == "name":
            next_name = str(value).strip()
            if not next_name:
                continue
            item.name = next_name
        elif field == "units":
            item.units = str(value).strip() or item.units
        elif field == "price":
            item.price = Decimal(str(value)) if value not in (None, "") else None
        elif field == "notes":
            item.notes = str(value).strip() or None
        else:
            setattr(item, field, value)
        session.add(item)

    session.commit()
