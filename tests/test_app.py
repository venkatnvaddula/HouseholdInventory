from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db_session
from app.main import create_app
from app.models.base import Base
from app.models.household import Household


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    Base.metadata.create_all(engine)
    with testing_session_local() as session:
        session.add(Household(id=1, name="Primary Household"))
        session.commit()

    def override_get_db_session() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_item_adds_inventory_row(client: TestClient) -> None:
    response = client.post(
        "/items",
        data={
            "name": "Rice",
            "category": "Food",
            "category_custom": "",
            "count": "2",
            "size": "2.5",
            "units": "kg",
            "location": "Pantry",
            "location_custom": "",
            "price": "8.99",
            "purchase_date": "2026-04-19",
            "expiry_date": "2026-12-31",
            "notes": "Basmati",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Rice" in response.text
    assert "Basmati" in response.text


def test_edit_item_updates_existing_inventory_row(client: TestClient) -> None:
    client.post(
        "/items",
        data={
            "name": "Soap",
            "category": "Personal Care",
            "category_custom": "",
            "count": "3",
            "size": "1",
            "units": "bars",
            "location": "Bathroom",
            "location_custom": "",
            "price": "4.50",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Original",
        },
    )

    response = client.post(
        "/items/1",
        data={
            "name": "Soap Refill",
            "category": "Household",
            "category_custom": "",
            "count": "4",
            "size": "1",
            "units": "packs",
            "location": "Storage",
            "location_custom": "",
            "price": "10.25",
            "purchase_date": "2026-04-20",
            "expiry_date": "",
            "notes": "Updated",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Soap Refill" in response.text
    assert "Updated" in response.text
    assert "Soap</td>" not in response.text


def test_items_page_renders_double_click_inline_editing(client: TestClient) -> None:
    client.post(
        "/items",
        data={
            "name": "Milk",
            "category": "Food",
            "category_custom": "",
            "count": "1",
            "size": "1",
            "units": "gallon",
            "location": "Fridge",
            "location_custom": "",
            "price": "5.25",
            "purchase_date": "2026-04-19",
            "expiry_date": "2026-04-25",
            "notes": "2%",
        },
    )

    response = client.get("/items")

    assert response.status_code == 200
    assert "1 item in current inventory" in response.text
    assert 'class="row-cell-display"' in response.text
    assert 'class="row-edit-input row-inline-editor"' in response.text
    assert 'class="row-edit-input row-inline-editor row-inline-editor-wide"' in response.text
    assert 'class="inventory-editor-row"' in response.text
    assert '>Save<' in response.text
    assert 'class="button button-secondary button-small row-mobile-edit-trigger"' in response.text
    assert 'id="mobile-editor-dock" class="mobile-editor-dock"' in response.text
    assert 'id="mobile-editor-save" class="button" type="submit"' in response.text
    assert 'row.addEventListener(\'dblclick\'' in response.text
    assert 'longPressDelayMs = 450' in response.text
    assert 'row.querySelector(\'.row-mobile-edit-trigger\')?.addEventListener(\'click\'' in response.text
    assert 'event.pointerType !== \'touch\'' in response.text
    assert 'event.target.closest(\'td[data-column-key]\')' in response.text
    assert 'focusInlineEditor(firstInput);' in response.text
    assert 'mobileEditorSave?.setAttribute(\'form\'' in response.text
    assert 'mobileEditorDock?.classList.add(\'is-active\')' in response.text
    assert 'document.addEventListener(\'keydown\'' in response.text
    assert "['Escape', 'Esc'].includes(event.key)" in response.text
    assert 'document.addEventListener(\'pointerdown\'' in response.text
    assert 'closeInlineEditor(activeEditingRow);' in response.text
    assert 'class="table-actions table-actions-compact row-action-group row-action-group-default"' in response.text
    assert 'action="/items/1?search=&sort_by=expiry_date&sort_dir=asc"' in response.text


def test_search_filters_inventory_results(client: TestClient) -> None:
    client.post(
        "/items",
        data={
            "name": "Tomato Soup",
            "category": "Food",
            "category_custom": "",
            "count": "2",
            "size": "1",
            "units": "cans",
            "location": "Pantry",
            "location_custom": "",
            "price": "",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Dinner",
        },
    )
    client.post(
        "/items",
        data={
            "name": "Shampoo",
            "category": "Personal Care",
            "category_custom": "",
            "count": "1",
            "size": "1",
            "units": "bottle",
            "location": "Bathroom",
            "location_custom": "",
            "price": "",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Hair",
        },
    )

    response = client.get("/items?search=Soup")

    assert response.status_code == 200
    assert "1 item in current inventory" in response.text
    assert "Tomato Soup" in response.text
    assert "Shampoo" not in response.text


def test_export_csv_returns_matching_inventory_rows(client: TestClient) -> None:
    client.post(
        "/items",
        data={
            "name": "Pasta",
            "category": "Food",
            "category_custom": "",
            "count": "5",
            "size": "1",
            "units": "boxes",
            "location": "Pantry",
            "location_custom": "",
            "price": "12.00",
            "purchase_date": "2026-04-19",
            "expiry_date": "2027-01-01",
            "notes": "Whole wheat",
        },
    )
    client.post(
        "/items",
        data={
            "name": "Dish Soap",
            "category": "Household",
            "category_custom": "",
            "count": "1",
            "size": "1",
            "units": "bottle",
            "location": "Kitchen",
            "location_custom": "",
            "price": "3.99",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Sink",
        },
    )

    response = client.get("/items/export.csv?search=Pasta")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="all-items.csv"'
    assert "id,name,category,count,size,units,location,price,purchase_date,expiry_date,notes" in response.text
    assert "Pasta,Food,5,1,boxes,Pantry,12.00,2026-04-19,2027-01-01,Whole wheat" in response.text
    assert "Dish Soap" not in response.text


def test_history_export_includes_deleted_items_with_timestamps(client: TestClient) -> None:
    client.post(
        "/items",
        data={
            "name": "Olive Oil",
            "category": "Food",
            "category_custom": "",
            "count": "1",
            "size": "1",
            "units": "bottle",
            "location": "Kitchen",
            "location_custom": "",
            "price": "15.00",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Cooking",
        },
    )

    client.post(
        "/items/bulk-delete",
        data={
            "item_ids": ["1"],
            "search": "",
            "sort_by": "expiry_date",
            "sort_dir": "asc",
        },
    )

    current_response = client.get("/items")
    history_response = client.get("/items/export-history.csv")

    assert current_response.status_code == 200
    assert "Olive Oil" not in current_response.text
    assert history_response.status_code == 200
    assert history_response.headers["content-disposition"] == 'attachment; filename="inventory-history.csv"'
    assert "created_at,updated_at,deleted_at" in history_response.text
    assert "Olive Oil,Food,1,1,bottle,Kitchen,15.00,2026-04-19,,Cooking," in history_response.text
    olive_row = next(line for line in history_response.text.splitlines() if "Olive Oil" in line)
    assert olive_row.split(",")[-1] != ""


def test_bulk_delete_removes_selected_items(client: TestClient) -> None:
    client.post(
        "/items",
        data={
            "name": "Beans",
            "category": "Food",
            "category_custom": "",
            "count": "2",
            "size": "1",
            "units": "cans",
            "location": "Pantry",
            "location_custom": "",
            "price": "",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Protein",
        },
    )
    client.post(
        "/items",
        data={
            "name": "Toothpaste",
            "category": "Personal Care",
            "category_custom": "",
            "count": "1",
            "size": "1",
            "units": "tube",
            "location": "Bathroom",
            "location_custom": "",
            "price": "",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Mint",
        },
    )

    response = client.post(
        "/items/bulk-delete",
        data={
            "item_ids": ["1"],
            "search": "",
            "sort_by": "expiry_date",
            "sort_dir": "asc",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Beans" not in response.text
    assert "Toothpaste" in response.text


def test_bulk_edit_name_updates_selected_items(client: TestClient) -> None:
    client.post(
        "/items",
        data={
            "name": "Trail Mix",
            "category": "Food",
            "category_custom": "",
            "count": "2",
            "size": "1",
            "units": "bags",
            "location": "Pantry",
            "location_custom": "",
            "price": "",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Snack",
        },
    )
    client.post(
        "/items",
        data={
            "name": "Granola",
            "category": "Food",
            "category_custom": "",
            "count": "1",
            "size": "1",
            "units": "box",
            "location": "Pantry",
            "location_custom": "",
            "price": "",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Breakfast",
        },
    )

    response = client.post(
        "/items/bulk-update",
        data={
            "item_ids": ["1"],
            "field": "name",
            "text_value": "Mixed Nuts",
            "number_value": "",
            "date_value": "",
            "category_choice": "Food",
            "category_custom": "",
            "location_choice": "Pantry",
            "location_custom": "",
            "search": "",
            "sort_by": "expiry_date",
            "sort_dir": "asc",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Mixed Nuts" in response.text
    assert "Trail Mix" not in response.text
    assert "Granola" in response.text