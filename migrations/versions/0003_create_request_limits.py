"""create shared request limits

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_limits",
        sa.Column("key", sa.CHAR(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_request_limits_window_start", "request_limits", ["window_start"])
    op.execute("ALTER TABLE request_limits ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("request_limits")
