"""Initial household inventory schema."""

from alembic import op
import sqlalchemy as sa


revision = "20260419_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "household_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="Uncategorized"),
        sa.Column("quantity", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default="item"),
        sa.Column("location", sa.String(length=80), nullable=False, server_default="Unassigned"),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_items_expiry_date", "items", ["expiry_date"])
    op.create_index("ix_items_household_id", "items", ["household_id"])
    op.create_index("ix_items_name", "items", ["name"])

    op.execute(
        sa.text(
            """
            INSERT INTO households (id, name)
            VALUES (1, 'Primary Household')
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_items_name", table_name="items")
    op.drop_index("ix_items_household_id", table_name="items")
    op.drop_index("ix_items_expiry_date", table_name="items")
    op.drop_table("items")
    op.drop_table("household_members")
    op.drop_table("users")
    op.drop_table("households")
