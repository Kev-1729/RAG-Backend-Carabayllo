import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    MetaData,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSION = 1024


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class DocumentModel(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("page_count > 0", name="page_count_positive"),
        CheckConstraint("superseded_by_id <> id", name="not_superseded_by_itself"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(CHAR(64), unique=True)
    page_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT")
    )


class ChunkModel(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    page: Mapped[int]
    chunk_index: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role_valid"),
        CheckConstraint("char_length(content) > 0", name="content_not_empty"),
        CheckConstraint(
            "role <> 'user' OR char_length(content) <= 2000",
            name="question_max_length",
        ),
        CheckConstraint(
            "role = 'assistant' OR (model IS NULL AND input_tokens IS NULL "
            "AND output_tokens IS NULL AND latency_ms IS NULL)",
            name="metrics_only_for_assistant",
        ),
        Index(
            "ix_messages_conversation_id_created_at", "conversation_id", "created_at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT")
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RatingModel(Base):
    __tablename__ = "ratings"
    __table_args__ = (CheckConstraint("stars BETWEEN 1 AND 5", name="stars_range"),)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), primary_key=True
    )
    stars: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MessageReferenceModel(Base):
    __tablename__ = "message_references"
    __table_args__ = (
        UniqueConstraint("message_id", "rank"),
        CheckConstraint("rank >= 1", name="rank_positive"),
        Index("ix_message_references_chunk_id", "chunk_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), primary_key=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="RESTRICT"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger)
    score: Mapped[float] = mapped_column(Float)
