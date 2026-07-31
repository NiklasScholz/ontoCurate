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


class StatementResponseWithOriginal(StatementResponse):
    original: str


class CurrentAndOriginalStatement(BaseModel):
    current: StatementResponse
    original: StatementResponse


class StatementEdit(BaseModel):
    subject: str | None = None
    predicate: str | None = None
    object_value: str | None = None
    object_iri: str | None = None


class IncomingEdge(BaseModel):
    predicate: str
    subject: str


class OutgoingEdge(BaseModel):
    predicate: str
    object: str


class EntityNeighborhoodResponse(BaseModel):
    incoming: list[IncomingEdge]
    outgoing: list[OutgoingEdge]


class StatementIdResponse(BaseModel):
    id: str


class DeduplicationCountResponse(BaseModel):
    total_count: int
    pending_count: int


class TextSpan(BaseModel):
    start: int
    end: int


class RelatedSpansResponse(BaseModel):
    subject_spans: list[TextSpan]
    object_spans: list[TextSpan]
