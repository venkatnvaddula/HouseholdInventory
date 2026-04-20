"""Convert item quantity to float."""

from alembic import op
import sqlalchemy as sa


revision = "20260419_0002"
down_revision = "20260419_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE items ALTER COLUMN quantity DROP DEFAULT")
    op.alter_column(
        "items",
        "quantity",
        existing_type=sa.String(length=32),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="NULLIF(quantity, '')::double precision",
    )
    op.execute("ALTER TABLE items ALTER COLUMN quantity SET DEFAULT 1.0")


def downgrade() -> None:
    op.execute("ALTER TABLE items ALTER COLUMN quantity DROP DEFAULT")
    op.alter_column(
        "items",
        "quantity",
        existing_type=sa.Float(),
        type_=sa.String(length=32),
        existing_nullable=False,
        postgresql_using="quantity::text",
    )
    op.execute("ALTER TABLE items ALTER COLUMN quantity SET DEFAULT '1'")