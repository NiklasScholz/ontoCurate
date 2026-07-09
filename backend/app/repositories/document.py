from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, document_id: UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: UUID) -> list[Document]:
        result = await self.session.execute(
            select(Document).where(Document.workspace_id == workspace_id)
        )
        return list(result.scalars().all())

    async def create_pdf(
        self, workspace_id: UUID, filename: str, raw_bytes: bytes, content_hash: str
    ) -> Document:
        doc = Document(
            workspace_id=workspace_id,
            filename=filename,
            file_type="pdf",
            raw_bytes=raw_bytes,
            content_hash=content_hash,
        )
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def create_markdown(
        self, workspace_id: UUID, filename: str, source_content: str, content_hash: str
    ) -> Document:
        doc = Document(
            workspace_id=workspace_id,
            filename=filename,
            file_type="markdown",
            source_content=source_content,
            content_hash=content_hash,
        )
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def get_by_hash(
        self, workspace_id: UUID, content_hash: str
    ) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.workspace_id == workspace_id,
                Document.content_hash == content_hash,
            )
        )
        return result.scalar_one_or_none()

    async def set_title(self, document_id: UUID, title: str) -> None:
        doc = await self.get_by_id(document_id)
        if doc:
            doc.title = title
            await self.session.commit()

    async def set_source_content(self, document_id: UUID, content: str) -> None:
        doc = await self.get_by_id(document_id)
        if doc:
            doc.source_content = content
            await self.session.commit()

    async def delete(self, document_id: UUID) -> None:
        doc = await self.get_by_id(document_id)
        if doc:
            await self.session.delete(doc)
            await self.session.commit()

    async def delete_all_for_workspace(self, workspace_id: UUID) -> None:
        await self.session.execute(
            delete(Document).where(Document.workspace_id == workspace_id)
        )
        await self.session.commit()
