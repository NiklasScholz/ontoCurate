from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RunDocumentResponse(BaseModel):
    document_id: UUID
    status: str
    task_name: str
    model_config = {"from_attributes": True}


class RunResponse(BaseModel):
    id: UUID
    model: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunDetailResponse(RunResponse):
    status: str
    documents: list[RunDocumentResponse]


class StatementDecision(BaseModel):
    id: str
    action: str


class DecideRequest(BaseModel):
    decisions: list[StatementDecision]
    min_confidence: float | None = None


class BulkAcceptRequest(BaseModel):
    min_confidence: float = 0.9


class StatementEdit(BaseModel):
    subject: str | None = None
    predicate: str | None = None
    object_value: str | None = None
    object_iri: str | None = None
