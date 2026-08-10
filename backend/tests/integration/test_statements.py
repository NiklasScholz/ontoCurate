import uuid

from test_utils import (
    activity_count,
    add_member,
    add_statement,
    as_user,
    create_workspace,
    find_candidate_id,
    register_user,
    setup_workspace_with_statement,
    sparql_count,
)

from app.store.client import data_graph

SUBJECT = "http://example.org/s"
PREDICATE = "http://example.org/p"
OBJECT_VALUE = "o"


class TestAcceptStatementEndpoint:
    async def test_owner_can_accept(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 200
        assert resp.json()["id"] != stmt_id

        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "{OBJECT_VALUE}"
                }}
            }}
        """
        assert sparql_count(data_sparql) == 1
        assert activity_count(workspace_id, "AcceptingActivity") == 1

    async def test_editor_can_accept(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 200
        assert resp.json()["id"] != stmt_id

        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "{OBJECT_VALUE}"
                }}
            }}
        """
        assert sparql_count(data_sparql) == 1
        assert activity_count(workspace_id, "AcceptingActivity") == 1

    async def test_non_member_cannot_accept(self, client, tmp_path):
        workspace_id, stmt_id, _ = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, _, non_member_token = await register_user(client, "no member")
        as_user(client, non_member_token)
        resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 403

    async def test_unknown_workspace(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.post(
            f"/statements/{uuid.uuid4()}/accept",
            params={"statement_id": "https://example.org/does-not-exist"},
        )
        assert resp.status_code == 403

    async def test_unknown_statement(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        resp = await client.post(
            f"/statements/{workspace_id}/accept",
            params={"statement_id": "https://example.org/does-not-exist"},
        )
        assert resp.status_code == 422

    async def test_accepting_twice(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 422
        assert activity_count(workspace_id, "AcceptingActivity") == 1

    async def test_edit_reject_accept_reject(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        edit_resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={"object_value": "edited-value"},
        )
        edited_id = edit_resp.json()["id"]

        reject_resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": edited_id}
        )
        rejected_id = reject_resp.json()["id"]

        resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": rejected_id}
        )
        accepted_id = resp.json()["id"]
        assert resp.status_code == 200
        assert activity_count(workspace_id, "AcceptingActivity") == 1
        assert activity_count(workspace_id, "RejectingActivity") == 1

        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "edited-value"
                }}
            }}
        """

        assert sparql_count(data_sparql) == 1

        reject_resp2 = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": accepted_id}
        )

        assert reject_resp2.status_code == 200
        assert activity_count(workspace_id, "AcceptingActivity") == 1
        assert activity_count(workspace_id, "RejectingActivity") == 2

        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "edited-value"
                }}
            }}
        """
        assert sparql_count(data_sparql) == 0


class TestBulkAcceptEndpoint:
    async def test_owner_can_bulk_accept_multiple_statements(self, client, tmp_path):
        workspace_id, stmt_id_1, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        stmt_id_2 = add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/s2",
            "http://example.org/p2",
            "o2",
        )

        resp = await client.post(
            f"/statements/{workspace_id}/bulk_accept",
            json=[stmt_id_1, stmt_id_2],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        # response order matches request order, and each is a new (accepted) id
        assert body[0]["id"] != stmt_id_1
        assert body[1]["id"] != stmt_id_2
        assert body[0]["subject"] == "http://example.org/s"
        assert body[1]["subject"] == "http://example.org/s2"

        assert activity_count(workspace_id, "AcceptingActivity") == 2

        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "{OBJECT_VALUE}"
                }}
            }}
        """
        assert sparql_count(data_sparql) == 1
        data_sparql_2 = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <http://example.org/s2> <http://example.org/p2> "o2"
                }}
            }}
        """
        assert sparql_count(data_sparql_2) == 1

    async def test_editor_can_bulk_accept(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.post(
            f"/statements/{workspace_id}/bulk_accept",
            json=[stmt_id],
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_non_member_cannot_bulk_accept(self, client, tmp_path):
        workspace_id, stmt_id, _ = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, _, non_member_token = await register_user(client, "no member")
        as_user(client, non_member_token)
        resp = await client.post(
            f"/statements/{workspace_id}/bulk_accept",
            json=[stmt_id],
        )
        assert resp.status_code == 403

    async def test_unknown_workspace(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.post(
            f"/statements/{uuid.uuid4()}/bulk_accept",
            json=["https://example.org/does-not-exist"],
        )
        assert resp.status_code == 403

    async def test_empty_list_returns_empty(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.post(
            f"/statements/{workspace_id}/bulk_accept",
            json=[],
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_already_accepted_statement_in_batch_fails(self, client, tmp_path):
        workspace_id, stmt_id_1, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        stmt_id_2 = add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/s2",
            "http://example.org/p2",
            "o2",
        )
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id_1}
        )

        resp = await client.post(
            f"/statements/{workspace_id}/bulk_accept",
            json=[stmt_id_1, stmt_id_2],
        )
        assert resp.status_code == 422
        assert activity_count(workspace_id, "AcceptingActivity") == 1

        data_sparql_2 = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <http://example.org/s2> <http://example.org/p2> "o2"
                }}
            }}
        """
        assert sparql_count(data_sparql_2) == 0


class TestRejectStatementEndpoint:
    async def test_owner_can_reject(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 200
        assert resp.json()["id"] != stmt_id
        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "{OBJECT_VALUE}"
                }}
            }}
        """
        assert sparql_count(data_sparql) == 0
        assert activity_count(workspace_id, "RejectingActivity") == 1

    async def test_editor_can_reject(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 200
        assert resp.json()["id"] != stmt_id
        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "{OBJECT_VALUE}"
                }}
            }}
        """
        assert sparql_count(data_sparql) == 0
        assert activity_count(workspace_id, "RejectingActivity") == 1

    async def test_non_member_cannot_reject(self, client, tmp_path):
        workspace_id, stmt_id, _ = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, _, non_member_token = await register_user(client, "no member")
        as_user(client, non_member_token)
        resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 403

    async def test_rejecting_twice_in_row_accept_on_orig_stmt(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )

        resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 422
        resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 422
        assert activity_count(workspace_id, "RejectingActivity") == 1
        assert activity_count(workspace_id, "AcceptingActivity") == 0


class TestEditStatementEndpoint:
    async def test_owner_can_edit_object_value(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={"object_value": "new-value"},
        )
        assert resp.status_code == 200
        edited_id = resp.json()["id"]
        assert edited_id != stmt_id
        assert (
            find_candidate_id(workspace_id, PREDICATE, object_value="new-value")
            == edited_id
        )

    async def test_editor_can_edit_object_value(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={"object_value": "new-value"},
        )
        assert resp.status_code == 200
        edited_id = resp.json()["id"]
        assert edited_id != stmt_id
        assert (
            find_candidate_id(workspace_id, PREDICATE, object_value="new-value")
            == edited_id
        )

    async def test_editing_accepted_statement_removes_stale_data_graph_triple(
        self, client, tmp_path
    ):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        accept_resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        accepted_id = accept_resp.json()["id"]
        old_data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{data_graph(workspace_id)}> {{
                    <{SUBJECT}> <{PREDICATE}> "{OBJECT_VALUE}"
                }}
            }}
        """
        assert sparql_count(old_data_sparql) == 1
        resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": accepted_id},
            json={"object_value": "new-value"},
        )
        assert resp.status_code == 200
        assert sparql_count(old_data_sparql) == 0

    async def test_non_member_cannot_edit(self, client, tmp_path):
        workspace_id, stmt_id, _ = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, _, non_member_token = await register_user(client, "no member")
        as_user(client, non_member_token)
        resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={"object_value": "new-value"},
        )
        assert resp.status_code == 403

    async def test_malformed_object(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={"object_iri": "http://example.org/x", "object_value": "y"},
        )
        assert resp.status_code == 422

    async def test_send_edit_with_no_changes(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={},
        )
        assert resp.status_code == 422
        resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={"object_value": OBJECT_VALUE},
        )
        assert resp.status_code == 422


class TestResetStatementEndpoint:
    async def test_owner_can_reset_after_reject(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        reject_resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )
        rejected_id = reject_resp.json()["id"]

        resp = await client.post(
            f"/statements/{workspace_id}/reset", params={"statement_id": rejected_id}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["subject"] == SUBJECT
        assert body["object"] == OBJECT_VALUE

    async def test_noReset_withoutAcceptOrReject(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.post(
            f"/statements/{workspace_id}/reset", params={"statement_id": stmt_id}
        )
        assert resp.status_code == 422

    async def test_editor_can_reset_after_reject(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        reject_resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )
        rejected_id = reject_resp.json()["id"]

        resp = await client.post(
            f"/statements/{workspace_id}/reset", params={"statement_id": rejected_id}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["subject"] == SUBJECT
        assert body["object"] == OBJECT_VALUE

    async def test_non_member_cannot_reset(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        reject_resp = await client.post(
            f"/statements/{workspace_id}/reject", params={"statement_id": stmt_id}
        )
        rejected_id = reject_resp.json()["id"]
        _, _, outsider_token = await register_user(client, "outsider")
        as_user(client, outsider_token)
        resp = await client.post(
            f"/statements/{workspace_id}/reset", params={"statement_id": rejected_id}
        )
        assert resp.status_code == 403


class TestGetCurrentStatementEndpoint:
    async def test_returns_latest_version_after_edit(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        edit_resp = await client.patch(
            f"/statements/{workspace_id}/edit",
            params={"statement_id": stmt_id},
            json={"object_value": "new-value"},
        )
        edited_id = edit_resp.json()["id"]

        resp = await client.get(
            f"/statements/{workspace_id}/statements/{stmt_id}/current"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == edited_id
        assert body["object"] == "new-value"

    async def test_unknown_workspace(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.get(
            f"/statements/{uuid.uuid4()}/statements/https://example.org/x/current"
        )
        assert resp.status_code == 404
