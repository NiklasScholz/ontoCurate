from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    title: str | None

    model_config = {"from_attributes": True}


class DocumentTitleUpdate(BaseModel):
    title: str
