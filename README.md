# HouseholdInventory
Keep track of all the things at home!

# Goal
Keep track of household items with information to help to use them before expiration, avoid re-buying the same things, just keeping track of things, ..

1. Should be a webpage / app that can be used in small number of devices in the household
2. Should be easy to scan or enter the details

- Basic information includes things like id, name, category, price, purchase_date, expiry_date, notes


Create a FastAPI household inventory app with PostgreSQL.

# Requirements:
- SQLAlchemy 2.x models and Alembic migrations
- Jinja2 templates with HTMX for interactions
- Mobile-first responsive UI
- Shared inventory model scoped by household_id
- Initial tables: households, users, household_members, items
- Item fields: name, category, count, size, units, location, price optional, purchase_date, expiry_date, notes
- Pages: item list, add item, edit item
- Expiring soon filter
- docker-compose for local Postgres
- pyproject.toml-based setup
- pytest smoke test for app startup
- clean app package structure
 
## Basic v1 scope: shared list, add item, edit item, delete item, expiring soon

# Stack
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Jinja2 + HTMX

# v1 Data Model
- households
- users
- household_members
- items

Items include:
- id
- household_id
- name
- category
- count
- size
- units
- location
- price
- purchase_date
- expiry_date
- notes

# Local Development
1. Copy `.env.example` to `.env`
2. Start PostgreSQL with `docker compose up -d`
3. Install dependencies with `pip install -e .[dev]`
4. Run migrations with `alembic upgrade head`
5. Start the app with `uvicorn app.main:app --reload`

# Initial Pages
- `/items` inventory list
- `/items/new` add item form
- `/items/{id}/edit` edit item form
- `/health` health check