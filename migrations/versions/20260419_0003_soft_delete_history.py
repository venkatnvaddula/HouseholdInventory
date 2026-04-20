"""Add soft delete tracking to items."""

from alembic import op
import sqlalchemy as sa


revision = "20260419_0003"
down_revision = "20260419_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_items_deleted_at", "items", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_items_deleted_at", table_name="items")
    op.drop_column("items", "deleted_at")