from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class AnalysisBaseModel(BaseModel):
    def __getitem__(self, key):
        return getattr(self, key)


class AnalysisRequest(AnalysisBaseModel):
    """This is used for basic call and response analyses"""

    analysis_name: str
    inputs: dict[str, Any]
    request_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)


class AnalysisStreamRequest(AnalysisRequest):
    """This is used only for stream analyses

    iterables are

    """

    max_iterations: int = 100
    iterables: dict[str, list[Iterable]] | None = None
    update_interval: float = 0.1

    @classmethod
    @field_validator("iterables")
    def iterable_validator(cls, iterables):

        vals = iterables.values()
        first_item_len = len(vals[0])
        if not all(len(item) == first_item_len for item in vals):
            raise ValueError("All iterable items in iterables must have same length")

        return iterables


class StreamUpdate(AnalysisBaseModel):
    x: float
    y: float
    z: float | None = Field(default=None)


class AnalysisStream(AnalysisBaseModel):
    x: list[float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    z: list[float] | None = None

    def append(self, other: AnalysisStream | StreamUpdate):

        if isinstance(other, StreamUpdate):
            self.x.append(other.x)
        else:
            self.x.extend(other.x)

        if isinstance(other, StreamUpdate):
            self.y.append(other.y)
        else:
            self.y.extend(other.y)

        if self.z is not None and other.z is not None:
            if isinstance(other, StreamUpdate):
                self.z.append(other.z)
            else:
                self.z.extend(other.z)

    def __add__(self, other: AnalysisStream | StreamUpdate):

        return self.append(other)


class AnalysisResult(AnalysisBaseModel):
    request_id: UUID | None = None
    status: Literal["error", "failed", "running", "completed"]
    analysis_name: str
    inputs: dict[str, Any] | None = None
    result: Any
    created_at: datetime
    finished_at: datetime | None = None

    def is_successful(self) -> bool:
        if self.status != "completed":
            raise RuntimeError(
                f"Analysis {self.request_id} did not complete succesfully"
            )
        return True


class AnalysisResponse(AnalysisBaseModel):
    request_id: UUID | None = None
    analysis_name: str
    inputs: dict[str, Any] | None = None
    error: str | None = None
    accepted: bool = False

    def is_accepted(self) -> bool:
        if not self.accepted:
            raise ValueError(
                f"Analysis '{self.analysis_name}' "
                f"with inputs {self.inputs} "
                f"was not accepted for processing: "
                f"{self.error}"
            )

        return True


# if __name__ == "__main__":
#     request = AnalysisRequest(analysis_name="double", inputs={"number": 5})
