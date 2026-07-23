from typing import Literal

from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    graph: Literal["data", "curation"] = "data"


class QueryBindingValue(BaseModel):
    value: str
    type: str


class QueryResultResponse(BaseModel):
    variables: list[str] = []
    rows: list[dict[str, QueryBindingValue | None]] = []
    boolean: bool | None = None
