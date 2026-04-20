"""Add email verification timestamp to users."""

from alembic import op
import sqlalchemy as sa


revision = "20260420_0006"
down_revision = "20260419_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")