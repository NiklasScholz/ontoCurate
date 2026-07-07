from pydantic import BaseModel


class StatementResponse(BaseModel):
    id: str
    subject: str
    predicate: str
    object: str
    origin: str
    curation_status: str
    created_at: str
    confidence: float | None
    text_span_start: int | None
    text_span_end: int | None


class StatementPatchBody(BaseModel):
    subject: str
    predicate: str
    object: str


class IncomingEdge(BaseModel):
    predicate: str
    subject: str


class OutgoingEdge(BaseModel):
    predicate: str
    object: str


class EntityNeighborhoodResponse(BaseModel):
    incoming: list[IncomingEdge]
    outgoing: list[OutgoingEdge]
