from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class WorkspaceCreate(BaseModel):
    name: str
    schema_name: str = "scholarlySchema"


class AddMemberRequest(BaseModel):
    user_info: str
    role: Literal["owner", "editor"]


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    role: str
    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    id: UUID
    email: str
    name: str | None
    picture: str | None
    role: str


class WorkspaceQueryRequest(BaseModel):
    query: str
    graph: Literal["data", "curation"] = "data"
