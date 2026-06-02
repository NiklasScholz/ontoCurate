from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunTask


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workspace_id: UUID, triggered_by: UUID, model: str) -> Run:
        run = Run(workspace_id=workspace_id, triggered_by=triggered_by, model=model)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_by_id(self, run_id: UUID) -> Run | None:
        result = await self.session.execute(select(Run).where(Run.id == run_id))
        return result.scalar_one_or_none()

    async def update_status(self, run_id: UUID, status: str) -> None:
        run = await self.get_by_id(run_id)
        if run:
            run.status = status
            await self.session.commit()

    async def add_task(self, run_id: UUID, document_id: UUID, task_name) -> RunTask:
        run_doc = RunTask(run_id=run_id, document_id=document_id, task_name=task_name)
        self.session.add(run_doc)
        await self.session.commit()
        await self.session.refresh(run_doc)
        return run_doc

    async def update_task_status(
        self, run_id: UUID, celery_task_id: UUID, status: str
    ) -> None:
        result = await self.session.execute(
            select(RunTask).where(
                RunTask.run_id == run_id,
                RunTask.celery_task_id == celery_task_id,
            )
        )
        run_task = result.scalar_one_or_none()
        if run_task:
            run_task.status = status
            await self.session.commit()
