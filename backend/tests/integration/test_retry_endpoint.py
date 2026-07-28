from uuid import UUID

from test_utils import (
    add_candidate_statements,
    as_user,
    count_candidate_statements_derived_from,
    create_workspace,
    register_user,
    upload_markdown,
)

from app.repositories.run import RunRepository


async def get_status(session, run_id: str, document_id: str) -> str:
    tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))
    task = next(t for t in tasks if str(t.document_id) == document_id)
    return task.status


class TestRetryDocument:
    async def test_owner_can_retry_failed_document(self, client, session):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        run_id, document_id = await upload_markdown(client, workspace_id)

        await RunRepository(session).update_document_status(
            UUID(run_id), UUID(document_id), "Failed"
        )

        resp = await client.post(f"/extraction/{run_id}/documents/{document_id}/retry")
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"

        tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))
        task = next(t for t in tasks if str(t.document_id) == document_id)
        assert task.status == "Queued"
        assert task.celery_task_id is None

    async def test_retry_clears_previous_extraction_output(
        self, client, session, tmp_path
    ):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        run_id, document_id = await upload_markdown(client, workspace_id)

        add_candidate_statements(
            tmp_path,
            workspace_id,
            '<http://example.org/s> <http://example.org/p> "o" .',
            document_id=document_id,
            run_id=run_id,
        )
        assert count_candidate_statements_derived_from(workspace_id, document_id) == 1
        # Simulate failed alignment stage
        await RunRepository(session).update_document_status(
            UUID(run_id), UUID(document_id), "Failed"
        )

        resp = await client.post(f"/extraction/{run_id}/documents/{document_id}/retry")
        assert resp.status_code == 202
        assert count_candidate_statements_derived_from(workspace_id, document_id) == 0

    async def test_non_member_cannot_retry(self, client, session):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        run_id, document_id = await upload_markdown(client, workspace_id)
        await RunRepository(session).update_document_status(
            UUID(run_id), UUID(document_id), "Failed"
        )
        _, _, non_member_token = await register_user(client, "no member")
        as_user(client, non_member_token)
        resp = await client.post(f"/extraction/{run_id}/documents/{document_id}/retry")
        assert resp.status_code == 403
        assert await get_status(session, run_id, document_id) == "Failed"

    async def test_retry_rejects_non_failed_document(self, client, session):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        run_id, document_id = await upload_markdown(
            client, workspace_id
        )  # Queue extraction
        resp = await client.post(f"/extraction/{run_id}/documents/{document_id}/retry")
        assert resp.status_code == 400

    async def test_retry_unknown_run_returns_404(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, document_id = await upload_markdown(client, workspace_id)
        fake_run_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.post(
            f"/extraction/{fake_run_id}/documents/{document_id}/retry"
        )
        assert resp.status_code == 404
