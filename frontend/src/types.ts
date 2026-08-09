export type Document = {
    id: string;
    filename: string;
    file_type: string;
    title: string | null;
    extracted_triples: number;
    pending_triples: number;
    created_at: string;
};

export type DocumentDetail = Document & {
    markdown: string;
};

export type CurrentAndOriginalStatement = {
    current: Statement;
    original: Statement;
};

export type Statement = {
    id: string;
    subject: string;
    predicate: string;
    object: string;
    object_is_uri: boolean;
    origin: string;
    curation_status: string;
    created_at: string;
    confidence: number;
    text_span_start: number | null;
    text_span_end: number | null;
};

export type TextSpan = {
    start: number;
    end: number;
};

export type RelatedSpans = {
    subject_spans: TextSpan[];
    object_spans: TextSpan[];
};

export type Graph = "data" | "curation";

export type BindingValue = { value: string; type: string };

export type QueryResult = {
    variables: string[];
    rows: Record<string, BindingValue | null>[];
    boolean?: boolean | null;
};
