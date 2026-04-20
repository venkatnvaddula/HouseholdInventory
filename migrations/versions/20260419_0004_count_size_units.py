"""Add count and rename quantity/unit fields on items."""

from alembic import op
import sqlalchemy as sa


revision = "20260419_0004"
down_revision = "20260419_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("count", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("items", "quantity", new_column_name="size")
    op.alter_column("items", "unit", new_column_name="units")
    op.alter_column("items", "count", server_default=None)


def downgrade() -> None:
    op.alter_column("items", "units", new_column_name="unit")
    op.alter_column("items", "size", new_column_name="quantity")
    op.drop_column("items", "count")