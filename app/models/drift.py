import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    text,
    BigInteger,
    CheckConstraint,
    Index,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base_class import Base


class DriftEvent(Base):
    __tablename__ = "drift_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE")
    )

    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    base_branch: Mapped[str] = mapped_column(String, nullable=False)
    head_branch: Mapped[str] = mapped_column(String, nullable=False)
    base_sha: Mapped[str] = mapped_column(String, nullable=False)
    head_sha: Mapped[str] = mapped_column(String, nullable=False)
    check_run_id: Mapped[int | None] = mapped_column(BigInteger)

    processing_phase: Mapped[str] = mapped_column(String, default="queued")
    drift_result: Mapped[str] = mapped_column(String, default="pending")

    overall_drift_score: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(String)
    agent_logs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(String)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    repository = relationship("Repository")

    __table_args__ = (
        CheckConstraint(
            "processing_phase IN ('queued', 'scouting', 'analyzing', 'generating', 'verifying', 'completed', 'failed')",
            name="check_processing_phase",
        ),
        CheckConstraint(
            "drift_result IN ('pending', 'clean', 'drift_detected', 'missing_docs', 'error')",
            name="check_drift_result",
        ),
        Index(
            "idx_drift_active_runs",
            "repo_id",
            postgresql_where=text("processing_phase NOT IN ('completed', 'failed')"),
        ),
    )


class DriftFinding(Base):
    __tablename__ = "drift_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    drift_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drift_events.id", ondelete="CASCADE")
    )

    code_path: Mapped[str] = mapped_column(String, nullable=False)
    doc_file_path: Mapped[str | None] = mapped_column(String)
    change_type: Mapped[str | None] = mapped_column(String)
    drift_type: Mapped[str | None] = mapped_column(String)

    drift_score: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    drift_event = relationship("DriftEvent")

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('added', 'modified', 'deleted')", name="check_finding_change_type"
        ),
        CheckConstraint(
            "drift_type IN ('outdated_docs', 'missing_docs', 'ambiguous_docs')",
            name="check_start_drift_type",
        ),
    )


class CodeChange(Base):
    __tablename__ = "code_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    drift_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drift_events.id", ondelete="CASCADE")
    )

    file_path: Mapped[str] = mapped_column(String, nullable=False)
    change_type: Mapped[str | None] = mapped_column(String)

    is_code: Mapped[bool | None] = mapped_column(Boolean, default=True)
    is_ignored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    drift_event = relationship("DriftEvent")

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('added', 'modified', 'deleted')", name="check_code_change_type"
        ),
    )
