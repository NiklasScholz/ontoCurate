export type Document = {
    id: string;
    filename: string;
    file_type: string;
    title: string | null;
    extracted_triples: number;
    pending_triples: number;
};

export type DocumentDetail = Document & {
    markdown: string;
};

export type Statement = {
    id: string;
    subject: string;
    predicate: string;
    object: string;
    origin: string;
    curation_status: string;
    created_at: string;
    confidence: number;
    text_span_start: number | null;
    text_span_end: number | null;
};
