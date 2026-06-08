from app.routes.extraction import derive_run_status


# Test for status logic
class TestDeriveRunStatus:
    def test_no_tasks_returns_queued(self):
        assert derive_run_status([]) == "queued"

    def test_all_queued_returns_queued(self):
        assert derive_run_status(["queued", "queued"]) == "queued"

    def test_any_extracting_returns_running(self):
        assert derive_run_status(["extracting"]) == "running"

    def test_any_converting_returns_running(self):
        assert derive_run_status(["converting"]) == "running"

    def test_mixed_extracting_and_done_returns_running(self):
        assert derive_run_status(["done", "extracting"]) == "running"

    def test_extracting_takes_priority_over_failed(self):
        assert derive_run_status(["failed", "extracting"]) == "running"

    def test_all_done_returns_completed(self):
        assert derive_run_status(["done", "done"]) == "completed"

    def test_any_failed_returns_failed(self):
        assert derive_run_status(["done", "failed"]) == "failed"

    def test_all_failed_returns_failed(self):
        assert derive_run_status(["failed", "failed"]) == "failed"
