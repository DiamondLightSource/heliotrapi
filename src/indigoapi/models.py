from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel


class AnalysisBaseModel(BaseModel):
    def __getitem__(self, key):
        return getattr(self, key)


class AnalysisRequest(AnalysisBaseModel):
    analysis_name: str
    inputs: dict
    request_id: UUID = uuid4()
    created_at: datetime = datetime.now()


class AnalysisResult(AnalysisBaseModel):
    request_id: UUID | None = None
    status: Literal["error", "failed", "running", "completed"]
    analysis_name: str
    result: Any
    created_at: datetime
    finished_at: datetime | None = None


if __name__ == "__main__":
    request = AnalysisRequest(analysis_name="double", inputs={"number": 5})

    print(request.request_id)
