from celery import chain, chord, group

#from .annotate import annotate_document_task
from .convert import convert_pdf_task
from .test import ping_task, slow_task
from .extract import extract_document_task
#from .lookup import lookup_task
#from .merge import merge_task


def _document_chain(document_id: str, file_type: str, run_id: str):
    """
    Per-document task chain.
    """
    extract = extract_document_task.si(document_id, run_id)

    # skip conversion for markdown files
    if file_type == "pdf":
        return chain(convert_pdf_task.si(document_id, run_id), extract)
    return chain(extract)


def build_pipeline(documents: list[dict], run_id: str):
    """
    Full Celery task graph for a pipeline run
    Requires chord when adding entity alignment & linking stages
    """
    return group(
        _document_chain(doc["document_id"], doc["file_type"], run_id)
        for doc in documents
    )
