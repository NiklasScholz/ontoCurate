from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Workspace]:
        result = await self.session.execute(select(Workspace))
        return list(result.scalars().all())

    async def get_by_id(self, workspace_id: UUID) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_member(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMember | None:
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, name: str) -> Workspace:
        workspace = Workspace(name=name)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def delete(self, workspace_id: UUID) -> None:
        workspace = await self.get_by_id(workspace_id)
        if workspace:
            await self.session.delete(workspace)
            await self.session.commit()
