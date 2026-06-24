from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunTask
from app.repositories.user import UserRepository


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, workspace_id: UUID, triggered_by: Optional[UUID], model: str
    ) -> Run:
        # If no triggering user supplied, create a system user
        if triggered_by is None:
            user_repo = UserRepository(self.session)
            user = await user_repo.get_by_email("system@localhost")
            if user is None:
                user = await user_repo.create(
                    email="system@localhost", password_encrypt=""
                )
            triggered_by = user.id

        run = Run(workspace_id=workspace_id, triggered_by=triggered_by, model=model)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_by_id(self, run_id: UUID) -> Run | None:
        result = await self.session.execute(select(Run).where(Run.id == run_id))
        return result.scalar_one_or_none()

    async def add_task(self, run_id: UUID, document_id: UUID, task_name) -> RunTask:
        run_doc = RunTask(run_id=run_id, document_id=document_id, task_name=task_name)
        self.session.add(run_doc)
        await self.session.commit()
        await self.session.refresh(run_doc)
        return run_doc

    async def update_document_status(
        self,
        run_id: UUID,
        document_id: UUID,
        status: str,
        celery_task_id: str | None = None,
        task_name: str | None = None,
    ) -> None:
        values: dict = {"status": status}
        if celery_task_id is not None:
            values["celery_task_id"] = celery_task_id
        if task_name is not None:
            values["task_name"] = task_name
        await self.session.execute(
            update(RunTask)
            .where(
                RunTask.run_id == run_id,
                RunTask.document_id == document_id,
            )
            .values(**values)
        )
        await self.session.commit()

    async def update_task_status(
        self, run_id: UUID, document_id: UUID, status: str
    ) -> None:
        await self.update_document_status(run_id, document_id, status)

    async def get_tasks_by_run(self, run_id: UUID) -> list[RunTask]:
        result = await self.session.execute(
            select(RunTask).where(RunTask.run_id == run_id)
        )
        return list(result.scalars().all())
