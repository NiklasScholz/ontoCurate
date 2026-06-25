from pydantic import BaseModel


class StatementResponse(BaseModel):
    id: str
    subject: str
    predicate: str
    object: str
    origin: str
    curation_status: str
    created_at: str
    confidence: float
    text_span_start: int
    text_span_end: int


class StatementPatchBody(BaseModel):
    subject: str
    predicate: str
    object: str


class IncomingEdge(BaseModel):
    subject: str
    predicate: str


class OutgoingEdge(BaseModel):
    subject: str
    predicate: str


class EntityNeighborhoodResponse(BaseModel):
    incoming: list[IncomingEdge]
    outgoing: list[OutgoingEdge]
