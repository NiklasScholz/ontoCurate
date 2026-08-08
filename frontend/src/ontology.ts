export const PACO = "https://ontocurate.app/provenance-and-curation-ontology/";
export const PACO_ACCEPTED = PACO + "accepted";
export const PACO_REJECTED = PACO + "rejected";
export const PACO_PENDING = PACO + "pending";
export const INTERNAL_NAMESPACE = "https://ontocurate.app/";

export function processEntityLabel(value: string): string {
    return value.split(/[/#]/).at(-1) ?? value;
}

export function processEntityLabelWithNamespace(value: string): string {
    const localName = processEntityLabel(value);
    return value.startsWith(INTERNAL_NAMESPACE) ? `onto:${localName}` : localName;
}
