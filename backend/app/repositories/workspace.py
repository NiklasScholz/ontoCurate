from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
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

    async def get_all_by_user(self, user_id: UUID) -> list[Workspace]:
        result = await self.session.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember)
            .where(WorkspaceMember.user_id == user_id)
        )
        return result.all()

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

    async def create(
        self,
        name: str,
        schema_path: str,
        alignment_config_path: str,
        provenance_config_path: str,
    ) -> Workspace:
        workspace = Workspace(
            name=name,
            schema_path=schema_path,
            alignment_config_path=alignment_config_path,
            provenance_config_path=provenance_config_path,
        )
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def create_with_id(
        self,
        name: str,
        workspace_id: UUID,
        schema_path: str,
        alignment_config_path: str,
        provenance_config_path: str,
    ) -> Workspace:
        workspace = Workspace(
            id=workspace_id,
            name=name,
            schema_path=schema_path,
            alignment_config_path=alignment_config_path,
            provenance_config_path=provenance_config_path,
        )
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def delete(self, workspace_id: UUID) -> None:
        workspace = await self.get_by_id(workspace_id)
        if workspace:
            await self.session.delete(workspace)
            await self.session.commit()


class WorkspaceMemberRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_role(self, workspace_id: UUID, user_id: UUID) -> str | None:
        result = await self.session.execute(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_member(
        self, workspace_id: UUID, user_id: UUID, role: str
    ) -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def list_members(self, workspace_id: UUID) -> list[WorkspaceMember]:
        result = await self.session.execute(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        )
        return list(result.scalars().all())

    async def list_members_with_users(
        self, workspace_id: UUID
    ) -> list[tuple[WorkspaceMember, User]]:
        result = await self.session.execute(
            select(WorkspaceMember, User)
            .join(User, WorkspaceMember.user_id == User.id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.role.desc())
        )
        return list(result.all())

    async def remove_member(self, workspace_id: UUID, user_id: UUID) -> None:
        result = await self.session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            await self.session.delete(member)
            await self.session.commit()
