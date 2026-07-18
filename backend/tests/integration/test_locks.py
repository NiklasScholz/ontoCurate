from test_utils import gen_workspace_id

from app.core.locks import workspace_alignment_lock


def test_second_acquire_fails_while_first_holds_lock():
    workspace_id = gen_workspace_id()
    first = workspace_alignment_lock(workspace_id)
    second = workspace_alignment_lock(workspace_id)
    assert first.acquire(blocking=False) is True
    assert second.acquire(blocking=False) is False
    first.release()


def test_lock_is_acquirable_again_after_release():
    workspace_id = gen_workspace_id()
    first = workspace_alignment_lock(workspace_id)
    assert first.acquire(blocking=False) is True
    first.release()
    second = workspace_alignment_lock(workspace_id)
    assert second.acquire(blocking=False) is True
    second.release()


def test_locks_for_different_workspaces_are_independent():
    lock_a = workspace_alignment_lock(gen_workspace_id())
    lock_b = workspace_alignment_lock(gen_workspace_id())
    assert lock_a.acquire(blocking=False) is True
    assert lock_b.acquire(blocking=False) is True
    lock_a.release()
    lock_b.release()
