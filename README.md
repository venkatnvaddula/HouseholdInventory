# Household Inventory

Household Inventory is a shared web app for tracking pantry items, toiletries, cleaning supplies, and other household stock across multiple people in the same home.

It is built as a server-rendered FastAPI application with PostgreSQL, SQLAlchemy, Alembic, and Jinja templates. The app is designed to work well on desktop and mobile, with fast editing directly from the inventory table.

## What It Does

The app helps a household keep one up-to-date inventory instead of maintaining separate lists or re-buying items that are already at home.

Current capabilities include:

- Shared household accounts with login/logout
- Email verification flow
- Password reset flow
- One household with multiple users and owner/member roles
- Add, edit, search, sort, and soft-delete inventory items
- Inline table editing on desktop and mobile
- Bulk edit and bulk delete
- CSV export for current inventory
- History export including deleted items
- Responsive layout for phone and desktop use

## Inventory Model

Each inventory item currently stores:

- `name`
- `category`
- `count`
- `size`
- `units`
- `location`
- `price` (optional)
- `purchase_date`
- `expiry_date`
- `notes`

The intent is:

- `count`: how many items/packages you have
- `size`: the amount per item
- `units`: the unit for that size, such as `oz`, `lbs`, `ml`, or `item`

Example:

- `count = 2`
- `size = 12`
- `units = oz`

This represents two 12 oz items.

## Stack

- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Jinja2
- HTMX
- pwdlib with Argon2 password hashing
- pytest

## Usage

### Create an Account

Open `/register` and provide:

- display name
- email
- password
- household name

The first account created for a household becomes the owner.

### Log In

Open `/login` and sign in with your household account.

If your account is not verified yet, request a verification link first.

### Verify Email

Open `/verify-email/request` to generate a verification link.

In development, the app shows a preview link directly in the browser instead of sending a real email.

### Reset Password

Open `/password-reset/request` to generate a password reset link.

In development, the app shows a preview link directly in the browser instead of sending a real email.

### Manage Household Members

Owners can open `/household/members` to:

- add members to the household
- create a new member account with a temporary password
- remove members
- assign owner or member role when adding a new member

### Work With Inventory

From `/items` you can:

- search items by name, category, location, and notes
- add a new item
- edit items inline in the table
- bulk edit selected rows
- bulk delete selected rows
- export current inventory to CSV
- export full history including deleted items

## Local Development

### Prerequisites

- Python 3.12+
- Docker
- Docker Compose

### Setup

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Start PostgreSQL:

```bash
docker compose up -d
```

3. Create or activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

4. Run database migrations:

```bash
alembic upgrade head
```

5. Start the app:

```bash
uvicorn app.main:app --reload
```

6. Open the app in your browser:

- `http://127.0.0.1:8000/register`
- `http://127.0.0.1:8000/login`
- `http://127.0.0.1:8000/items`

## Environment Variables

The app currently uses these settings from `.env`:

- `APP_ENV`
- `APP_NAME`
- `DATABASE_URL`
- `SESSION_SECRET`

Example values are defined in [.env.example](.env.example).

Important note:

- `SESSION_SECRET` should be changed from the development default before deploying anywhere real.

## Database and Migrations

Alembic migration files live in [migrations/versions](migrations/versions).

Current migration history includes:

- initial schema
- quantity-to-float migration
- soft delete support
- rename to `count`, `size`, and `units`
- user auth and household membership constraints

To apply the latest schema:

```bash
alembic upgrade head
```

## Tests

Run the test suite with:

```bash
python -m pytest -q
```

The test suite covers request-level flows such as:

- health checks
- authentication and registration
- protected inventory access
- household member management
- item CRUD flows
- search and export behavior
- inline editing render expectations

## Project Structure

```text
app/
  auth.py                Auth/session helpers
  config.py              App settings
  db.py                  SQLAlchemy engine and session
  main.py                FastAPI app factory
  models/                ORM models
  routes/                FastAPI route handlers
  services/              Business logic
  static/                CSS and frontend assets
  templates/             Jinja templates
migrations/              Alembic migrations
tests/                   Request-level tests
docker-compose.yml       Local PostgreSQL service
```

## Key Routes

- `/register` — create an account and household
- `/login` — log in
- `/logout` — log out
- `/items` — inventory list
- `/items/new` — add item page
- `/household/members` — member management page for owners
- `/items/export.csv` — current inventory CSV export
- `/items/export-history.csv` — inventory history export
- `/health` — health check

## Development Notes

A few implementation details matter when extending the app:

- Inventory is scoped by authenticated household membership, not a global household id.
- Deleted items are soft-deleted using `deleted_at` so they remain available in history export.
- The current UI is server-rendered, so many changes are best made in templates and route/service code rather than building a separate API-first frontend.
- Household display names in the UI strip backend uniqueness suffixes like trailing numbers.

## Deployment Notes

This app requires:

- a Python application server
- a PostgreSQL database
- session secret configuration

Platforms that fit better include:

- AWS
- Render
- Railway
- Fly.io
- a VPS

## Current Limitations

A few things are intentionally simple right now:

- no invite-token flow yet for new household members
- no multi-household switching per user

Those can be added later without changing the overall architecture.
