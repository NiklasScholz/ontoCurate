from celery import chain, chord, group

from .convert import convert_pdf_task
from .cross_document_align import align_cross_document_task
from .extract import extract_document_task
from .inner_document_align import align_document_task

# from .lookup import lookup_task
# from .merge import merge_task


def get_document_chain(document_id: str, file_type: str, run_id: str):
    """Per-document chain: (convert) -> extract -> inner-document alignment"""
    extract = extract_document_task.s(document_id, run_id)
    align = align_document_task.s()

    if file_type == "pdf":
        return chain(convert_pdf_task.si(document_id, run_id), extract, align)
    return chain(extract, align)


def build_pipeline(documents: list[dict], model: str, run_id: str, workspace_id: str):
    """
    Full Celery task graph for a pipeline run.
    """
    doc_group = group(
        get_document_chain(doc["document_id"], doc["file_type"], run_id)
        for doc in documents
    )
    if len(documents) < 2:
        return doc_group

    cross_doc = align_cross_document_task.si(workspace_id, run_id)
    return chord(doc_group, cross_doc)
