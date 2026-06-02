from fastapi import APIRouter

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/", status_code=202)
async def create_run():
    pass


@router.get("/{run_id}")
async def get_run():
    pass


@router.get("/{run_id}/statements")
async def get_run_statements():
    pass


@router.post("/{run_id}/statements/bulk_accept", status_code=202)
async def bulk_accept_statements():
    pass


@router.post("/{run_id}/statements/{statement_id:path}/accept", status_code=200)
async def accept_statement():
    pass


@router.post("/{run_id}/statements/{statement_id:path}/reject", status_code=200)
async def reject_statement():
    pass


@router.patch("/{run_id}/statements/{statement_id:path}", status_code=200)
async def edit_statement():
    pass


@router.get("/{run_id}/entities")
async def get_run_entities():
    pass


@router.get("/{run_id}/entities/{entity_uri:path}/statements")
async def get_run_entity_statements():
    pass
