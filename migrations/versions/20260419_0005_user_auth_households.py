"""Add user authentication fields and household membership uniqueness."""

from alembic import op
import sqlalchemy as sa


revision = "20260419_0005"
down_revision = "20260419_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=False, server_default="!"))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("users", "password_hash", server_default=None)
    op.alter_column("users", "is_active", server_default=None)
    op.create_unique_constraint(
        "uq_household_members_household_user",
        "household_members",
        ["household_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_household_members_household_user", "household_members", type_="unique")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "is_active")
    op.drop_column("users", "password_hash")