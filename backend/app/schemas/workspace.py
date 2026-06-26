from uuid import UUID

from pydantic import BaseModel


class WorkspaceCreate(BaseModel):
    name: str
    schema_path: str
    alignment_config_path: str
    provenance_config_path: str


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}
