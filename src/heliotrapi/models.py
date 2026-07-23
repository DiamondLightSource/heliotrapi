from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AnalysisBaseModel(BaseModel):
    def __getitem__(self, key):
        return getattr(self, key)


class AnalysisRequest(AnalysisBaseModel):
    analysis_name: str
    inputs: dict[str, Any]
    request_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    password: str | None = None


class AnalysisResult(AnalysisBaseModel):
    request_id: UUID | None = None
    status: Literal["error", "failed", "running", "completed"]
    analysis_name: str
    inputs: dict[str, Any] | None = None
    result: Any
    created_at: datetime
    finished_at: datetime | None = None


class AnalysisResponse(AnalysisBaseModel):
    request_id: UUID | None = None
    analysis_name: str
    inputs: dict[str, Any] | None = None
    details: str | None = None
    accepted: bool = False

    def is_accepted(self) -> bool:
        if not self.accepted:
            raise ValueError(
                f"Analysis '{self.analysis_name}' "
                f"with inputs {self.inputs} "
                f"was not accepted for processing: "
                f"{self.details}"
            )

        return True


# if __name__ == "__main__":
#     request = AnalysisRequest(analysis_name="double", inputs={"number": 5})
