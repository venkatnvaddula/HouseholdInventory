from collections.abc import Generator
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db_session
from app.main import create_app
from app.models.base import Base
from app.models.household import Household


def _extract_preview_path(response_text: str, route_prefix: str) -> str:
    match = re.search(rf'value="([^"]+/{route_prefix}\?token=[^"]+)"', response_text)
    assert match is not None
    return "/" + match.group(1).split("/", 3)[3]


def _verify_user(app_client: TestClient, email: str) -> None:
    response = app_client.post(
        "/verify-email/request",
        data={"email": email},
        follow_redirects=False,
    )
    assert response.status_code == 200
    verify_path = _extract_preview_path(response.text, "verify-email")
    verify_response = app_client.get(verify_path, follow_redirects=False)
    assert verify_response.status_code == 200


@pytest.fixture
def app_client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    Base.metadata.create_all(engine)

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


@pytest.fixture
def client(app_client: TestClient) -> TestClient:
    response = app_client.post(
        "/register",
        data={
            "display_name": "Venkat",
            "email": "venkat@example.com",
            "password": "supersecret123",
            "household_name": "Primary Household",
        },
        follow_redirects=False,
    )
    assert response.status_code == 201
    path = _extract_preview_path(response.text, "verify-email")
    verify_response = app_client.get(path, follow_redirects=False)
    assert verify_response.status_code == 200
    login_response = app_client.post(
        "/login",
        data={"email": "venkat@example.com", "password": "supersecret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303
    return app_client


def test_health_check_returns_ok(app_client: TestClient) -> None:
    response = app_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inventory_requires_login(app_client: TestClient) -> None:
    response = app_client.get("/items", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_register_requires_verification_before_login(app_client: TestClient) -> None:
    register_response = app_client.post(
        "/register",
        data={
            "display_name": "Venkat",
            "email": "venkat@example.com",
            "password": "supersecret123",
            "household_name": "Primary Household",
        },
        follow_redirects=False,
    )

    assert register_response.status_code == 201
    assert "Verify your email before logging in" in register_response.text

    login_response = app_client.post(
        "/login",
        data={"email": "venkat@example.com", "password": "supersecret123"},
        follow_redirects=False,
    )

    assert login_response.status_code == 400
    assert "Verify your email before logging in" in login_response.text


def test_household_visible_name_hides_numeric_suffix() -> None:
    household = Household(name="VV Household 3")

    assert household.visible_name == "VV Household"


def test_password_reset_flow_updates_password(app_client: TestClient) -> None:
    register_response = app_client.post(
        "/register",
        data={
            "display_name": "Venkat",
            "email": "venkat@example.com",
            "password": "supersecret123",
            "household_name": "Primary Household",
        },
        follow_redirects=False,
    )
    verify_path = _extract_preview_path(register_response.text, "verify-email")
    app_client.get(verify_path)

    reset_response = app_client.post(
        "/password-reset/request",
        data={"email": "venkat@example.com"},
        follow_redirects=False,
    )

    assert reset_response.status_code == 200
    reset_path = _extract_preview_path(reset_response.text, "password-reset")

    password_form_response = app_client.get(reset_path)
    assert password_form_response.status_code == 200

    submit_response = app_client.post(
        "/password-reset",
        data={
            "token": reset_path.split("token=", 1)[1],
            "password": "newsecret123",
            "confirm_password": "newsecret123",
        },
        follow_redirects=False,
    )

    assert submit_response.status_code == 200
    assert "Your password has been updated" in submit_response.text

    login_response = app_client.post(
        "/login",
        data={"email": "venkat@example.com", "password": "newsecret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303


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
    assert 'action="/logout"' in response.text
    assert '>Log out<' in response.text
    assert "Venkat" in response.text
    assert "1 item in inventory" in response.text
    assert 'class="row-cell-display"' in response.text
    assert 'class="row-edit-input row-inline-editor"' in response.text
    assert 'class="inventory-editor-row"' in response.text
    assert 'id="mobile-editor-dock" class="mobile-editor-dock"' in response.text
    assert 'row.addEventListener(\'dblclick\'' in response.text
    assert 'longPressDelayMs = 450' in response.text
    assert 'mobileEditorSave?.setAttribute(\'form\'' in response.text


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
    assert "1 item in inventory" in response.text
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


def test_owner_can_add_member_and_member_sees_shared_inventory(app_client: TestClient) -> None:
    register_response = app_client.post(
        "/register",
        data={
            "display_name": "Venkat",
            "email": "venkat@example.com",
            "password": "supersecret123",
            "household_name": "Primary Household",
        },
        follow_redirects=False,
    )
    assert register_response.status_code == 201
    owner_verify_path = _extract_preview_path(register_response.text, "verify-email")
    app_client.get(owner_verify_path, follow_redirects=False)
    owner_login_response = app_client.post(
        "/login",
        data={"email": "venkat@example.com", "password": "supersecret123"},
        follow_redirects=False,
    )
    assert owner_login_response.status_code == 303

    app_client.post(
        "/items",
        data={
            "name": "Coffee",
            "category": "Food",
            "category_custom": "",
            "count": "1",
            "size": "12",
            "units": "oz",
            "location": "Pantry",
            "location_custom": "",
            "price": "11.99",
            "purchase_date": "2026-04-19",
            "expiry_date": "",
            "notes": "Whole bean",
        },
    )

    add_member_response = app_client.post(
        "/household/members",
        data={
            "email": "spouse@example.com",
            "display_name": "Spouse",
            "password": "sharedhouse123",
            "role": "member",
        },
        follow_redirects=True,
    )

    assert add_member_response.status_code == 200
    assert "spouse@example.com" in add_member_response.text

    app_client.post("/logout", follow_redirects=False)

    _verify_user(app_client, "spouse@example.com")

    member_response = app_client.post(
        "/login",
        data={"email": "spouse@example.com", "password": "sharedhouse123"},
        follow_redirects=True,
    )

    assert member_response.status_code == 200
    assert "Coffee" in member_response.text
