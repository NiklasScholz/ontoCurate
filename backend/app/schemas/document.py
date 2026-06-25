from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    title: str | None
    extracted_triples: int
    pending_triples: int

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    markdown: str


class DocumentTitleUpdate(BaseModel):
    title: str
