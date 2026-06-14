"""Risk event patch shapes (FR-011/022) — patient acknowledges on /emergency."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RiskEventPatch(BaseModel):
    alone_status: Literal["alone", "with_someone"] = Field(alias="aloneStatus")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class RiskEventAckOut(BaseModel):
    id: UUID
    status: str
    alone_status: str | None = Field(default=None, alias="aloneStatus")
    acknowledged_at: datetime | None = Field(default=None, alias="acknowledgedAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
