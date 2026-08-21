from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.models.base import TimestampMixin


class AgentRun(Base, TimestampMixin):
    """AI triage run for an incident-worthy Observation."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_observation_id", "observation_id"),
        Index("ix_agent_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    root_cause_hypothesis: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    severity_assessment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AgentRun id={self.id} observation_id={self.observation_id} "
            f"status={self.status!r}>"
        )
