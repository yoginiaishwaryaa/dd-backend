import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    text,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base_class import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    installation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("installations.installation_id", ondelete="CASCADE")
    )
    repo_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_url: Mapped[str | None] = mapped_column(String)

    docs_root_path: Mapped[str | None] = mapped_column(String, default="/docs")
    target_branch: Mapped[str | None] = mapped_column(String, default="main")
    style_preference: Mapped[str | None] = mapped_column(String, default="professional")
    file_ignore_patterns: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    reviewer: Mapped[str | None] = mapped_column(String)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    installation = relationship(
        "Installation",
        primaryjoin="Repository.installation_id==Installation.installation_id",
        foreign_keys=[installation_id],
    )

    __table_args__ = (UniqueConstraint("installation_id", "repo_name"),)
