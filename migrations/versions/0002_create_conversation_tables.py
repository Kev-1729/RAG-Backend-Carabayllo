"""create conversation tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 17:11:25.507542

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_table(
        "messages",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role <> 'user' OR char_length(content) <= 2000",
            name=op.f("ck_messages_question_max_length"),
        ),
        sa.CheckConstraint(
            "role = 'assistant' OR (model IS NULL AND input_tokens IS NULL AND output_tokens IS NULL AND latency_ms IS NULL)",
            name=op.f("ck_messages_metrics_only_for_assistant"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')", name=op.f("ck_messages_role_valid")
        ),
        sa.CheckConstraint(
            "char_length(content) > 0", name=op.f("ck_messages_content_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "message_references",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "rank >= 1", name=op.f("ck_message_references_rank_positive")
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_message_references_chunk_id_chunks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_references_message_id_messages"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "message_id", "chunk_id", name=op.f("pk_message_references")
        ),
        sa.UniqueConstraint(
            "message_id", "rank", name=op.f("uq_message_references_message_id_rank")
        ),
    )
    op.create_index(
        "ix_message_references_chunk_id",
        "message_references",
        ["chunk_id"],
        unique=False,
    )
    op.create_table(
        "ratings",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("stars", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stars BETWEEN 1 AND 5", name=op.f("ck_ratings_stars_range")
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_ratings_message_id_messages"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_ratings")),
    )
    op.add_column("documents", sa.Column("superseded_by_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_documents_superseded_by_id_documents"),
        "documents",
        "documents",
        ["superseded_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_documents_not_superseded_by_itself"),
        "documents",
        "superseded_by_id <> id",
    )
    for table in ("conversations", "messages", "ratings", "message_references"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_documents_not_superseded_by_itself"), "documents", type_="check"
    )
    op.drop_constraint(
        op.f("fk_documents_superseded_by_id_documents"), "documents", type_="foreignkey"
    )
    op.drop_column("documents", "superseded_by_id")
    op.drop_table("ratings")
    op.drop_index("ix_message_references_chunk_id", table_name="message_references")
    op.drop_table("message_references")
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")
