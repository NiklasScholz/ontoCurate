import {
    ArrowLeftIcon,
    ArrowRightIcon,
    CheckIcon,
    ExternalLinkIcon,
    ListIcon,
    RotateCcwIcon,
    XIcon,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { client } from "../client.ts";
import Spinner from "../components/Spinner.tsx";
import type { CurrentAndOriginalStatement, Statement } from "../types.ts";
import MarkdownView, {
    type HighlightSpan,
} from "../components/MarkdownView.tsx";
import {
    INTERNAL_NAMESPACE,
    PACO_ACCEPTED,
    PACO_REJECTED,
    processEntityLabel,
} from "../ontology.ts";

function useRelatedSpans(
    docId: string | null,
    statement: Statement | undefined,
): HighlightSpan[] {
    const [spans, setSpans] = useState<HighlightSpan[]>([]);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSpans([]);

        if (docId === null || statement === undefined) {
            return;
        }

        const isLiteral =
            statement.text_span_start !== null &&
            statement.text_span_end !== null;
        const ownSpan = isLiteral
            ? {
                  start: statement.text_span_start as number,
                  end: statement.text_span_end as number,
                  role: "object" as const,
              }
            : null;
        if (ownSpan) {
            setSpans([ownSpan]);
        }

        let cancelled = false;
        client
            .GET("/documents/{document_id}/related-spans", {
                params: {
                    path: { document_id: docId },
                    query: {
                        subject: statement.subject,
                        // we handle the literal case on the frontend, no need to query
                        object: isLiteral ? undefined : statement.object,
                    },
                },
            })
            .then((res) => {
                if (cancelled || res.data === undefined) return;
                setSpans([
                    ...(ownSpan ? [ownSpan] : []),
                    ...res.data.subject_spans
                        .filter(
                            (s) =>
                                !(
                                    ownSpan &&
                                    s.start === ownSpan.start &&
                                    s.end === ownSpan.end
                                ),
                        )
                        .map((s) => ({
                            ...s,
                            role: "subject" as const,
                        })),
                    ...res.data.object_spans.map((s) => ({
                        ...s,
                        role: "object" as const,
                    })),
                ]);
            });

        return () => {
            cancelled = true;
        };
    }, [docId, statement]);

    return spans;
}

type Neighborhood = {
    incoming: { predicate: string; subject: string; status: string }[];
    outgoing: { predicate: string; object: string; status: string }[];
};

function statusColor(status: string): string {
    const styles = getComputedStyle(document.documentElement);
    if (status === PACO_ACCEPTED) {
        return styles.getPropertyValue("--color-nord14");
    }
    if (status === PACO_REJECTED) {
        return styles.getPropertyValue("--color-nord11");
    }
    return styles.getPropertyValue("--color-nord4");
}

function SvgMultilineText({
    x,
    y,
    text,
    maxWidth,
}: {
    x: number;
    y: number;
    text: string;
    maxWidth: number;
}) {
    const measureWidth = (str: string): number => {
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        return ctx.measureText(str).width;
    };

    const lines = useMemo(() => {
        const words = text.split(/\s+/);
        let result: string[] = [];
        let currentLine = "";

        for (const word of words) {
            const testLine = currentLine ? `${currentLine} ${word}` : word;
            const testWidth = measureWidth(testLine);

            if (testWidth <= maxWidth) {
                currentLine = testLine;
            } else {
                if (currentLine) {
                    result.push(currentLine);
                }
                if (measureWidth(word) > maxWidth) {
                    let charLine = "";
                    for (const char of word) {
                        const testCharLine = charLine + char;
                        if (measureWidth(testCharLine) <= maxWidth) {
                            charLine = testCharLine;
                        } else {
                            result.push(charLine);
                            charLine = char;
                        }
                    }
                    if (charLine) {
                        currentLine = charLine;
                    } else {
                        currentLine = "";
                    }
                } else {
                    currentLine = word;
                }
            }
        }

        if (currentLine) {
            result.push(currentLine);
        }

        if (result.length > 3) {
            result = result.slice(0, 3);
            result[2] += "...";
        }

        return result;
    }, [text, maxWidth]);

    const styles = getComputedStyle(document.documentElement);
    const nord0 = styles.getPropertyValue("--color-nord0");

    return (
        <text
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={nord0}
            fontSize="18"
        >
            {lines.map((line, i) => (
                <tspan
                    key={i}
                    x={x}
                    y={y + (i + 0.5 - lines.length / 2.0) * 20}
                >
                    {line}
                </tspan>
            ))}
        </text>
    );
}

function Neighbors({
    neighbors,
    incoming,
}: {
    neighbors: { node: string; predicate: string; status: string }[];
    incoming: boolean;
}) {
    const styles = getComputedStyle(document.documentElement);
    const nord4 = styles.getPropertyValue("--color-nord4");
    const MAX_NODES = 6;

    return neighbors
        .filter((_, i) => i < MAX_NODES)
        .map(({ node, predicate, status }, i) => {
            const ypos =
                (i + 0.5) * (500 / Math.min(neighbors.length, MAX_NODES));
            return (
                <Fragment key={i}>
                    <line
                        x1={incoming ? 100 : 700}
                        y1={ypos}
                        x2="400"
                        y2="250"
                        stroke={statusColor(status)}
                        strokeWidth="5"
                    />
                    {neighbors.length > MAX_NODES && i === MAX_NODES - 1 ? (
                        <SvgMultilineText
                            x={incoming ? 100 : 700}
                            y={ypos}
                            maxWidth={100}
                            text="..."
                        />
                    ) : (
                        <>
                            <circle
                                r="30"
                                cx={incoming ? 100 : 700}
                                cy={ypos}
                                fill={nord4}
                            />
                            <SvgMultilineText
                                x={incoming ? 250 : 550}
                                y={(ypos + 250) / 2}
                                maxWidth={100}
                                text={processEntityLabel(predicate)}
                            />
                            <SvgMultilineText
                                x={incoming ? 100 : 700}
                                y={ypos}
                                maxWidth={100}
                                text={processEntityLabel(node)}
                            />
                        </>
                    )}
                </Fragment>
            );
        });
}

function LocalGraphView({
    center,
    incoming,
    outgoing,
}: {
    center: string;
} & Neighborhood) {
    const styles = getComputedStyle(document.documentElement);
    const nord8 = styles.getPropertyValue("--color-nord8");

    return (
        <svg viewBox="0 0 800 500" className="h-full w-full">
            <Neighbors
                neighbors={incoming.map(({ subject, predicate, status }) => {
                    return { node: subject, predicate, status };
                })}
                incoming={true}
            />
            <Neighbors
                neighbors={outgoing.map(({ object, predicate, status }) => {
                    return { node: object, predicate, status };
                })}
                incoming={false}
            />
            <circle r="30" cx="400" cy="250" fill={nord8} />
            <SvgMultilineText
                x={400}
                y={250}
                maxWidth={100}
                text={processEntityLabel(center)}
            />
        </svg>
    );
}

function EntityView({
    workspaceId,
    entityId,
    statusRefresh,
}: {
    workspaceId: string;
    entityId: string;
    statusRefresh: string;
}) {
    const [neighborhood, setNeighborhood] = useState<Neighborhood | undefined>(
        undefined,
    );

    useEffect(() => {
        let cancelled = false;
        client
            .GET("/graph/{workspace_id}/neighborhood", {
                params: {
                    path: { workspace_id: workspaceId },
                    query: { entity_id: entityId },
                },
            })
            .then((res) => {
                if (cancelled) return;
                setNeighborhood(res.data);
            });
        return () => {
            cancelled = true;
        };
    }, [workspaceId, entityId, statusRefresh]);

    return neighborhood ? (
        <div className="h-full">
            <LocalGraphView
                center={entityId}
                incoming={neighborhood.incoming}
                outgoing={neighborhood.outgoing}
            />
        </div>
    ) : (
        <Spinner />
    );
}

// We currently do not support external links to documentation on the shipped schemas, all others can be inspected
function isExternalUrl(value: string): boolean {
    return /^https?:\/\//i.test(value) && !value.startsWith(INTERNAL_NAMESPACE);
}

function TextField({
    current,
    original,
    onChange,
    edgeClassName = "border-transparent",
}: {
    current: string;
    original: string;
    onChange: (newValue: string) => void;
    edgeClassName?: string;
}) {
    const [value, setValue] = useState<string>(current);

    return (
        <div
            className={`bg-nord6 flex h-28 flex-col justify-between gap-2 rounded-t border-t-4 p-2 ${edgeClassName}`}
        >
            <div className="flex h-full gap-1 font-mono text-sm wrap-anywhere">
                <textarea
                    className="h-full w-full"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    onBlur={() => {
                        if (value !== current) {
                            onChange(value);
                        }
                    }}
                />
                {isExternalUrl(current) && (
                    <a
                        href={current}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-nord10 shrink-0"
                        title={current}
                    >
                        <ExternalLinkIcon size={16} />
                    </a>
                )}
            </div>
            <div
                className={`flex justify-center gap-2 ${current === original && "hidden"}`}
            >
                <button
                    className="bg-nord4 flex h-7 w-12 items-center justify-center rounded"
                    onClick={() => onChange(original)}
                >
                    <RotateCcwIcon size={16} />
                </button>
            </div>
        </div>
    );
}

export default function CurationDetail({
    onClose,
    onPrevious,
    onNext,
    onChange,
    workspaceId,
    markdown,
    index,
    total,
    statement,
    docId,
}: {
    onClose: () => void;
    onPrevious: () => void;
    onNext: () => void;
    onChange: (update: Record<string, Statement>) => void;
    workspaceId: string;
    markdown: string | undefined;
    index: number;
    total: number;
    statement: CurrentAndOriginalStatement;
    docId: string | null;
}) {
    const relatedSpans = useRelatedSpans(docId, statement.current);

    return (
        <div
            className={`bg-nord6 flex h-full ${docId === null ? "w-[70vw]" : "w-full max-w-7xl"} flex-col gap-2 overflow-y-auto rounded p-4 shadow-xl ${statement.current.curation_status === PACO_ACCEPTED && "tint-accepted"} ${statement.current.curation_status === PACO_REJECTED && "tint-rejected"}`}
        >
            <div className="mb-4 flex justify-between gap-2">
                <div></div>
                <div className="flex gap-4">
                    <button
                        disabled={index === 0}
                        onClick={onPrevious}
                        className="bg-nord8 flex h-7 w-12 items-center justify-center rounded"
                    >
                        <ArrowLeftIcon size={16} />
                    </button>
                    <h1 className="text-center text-xl">
                        Triple {index + 1}/{total}
                    </h1>
                    <button
                        disabled={index === total - 1}
                        onClick={onNext}
                        className="bg-nord8 flex h-7 w-12 items-center justify-center rounded"
                    >
                        <ArrowRightIcon size={16} />
                    </button>
                </div>
                <button
                    onClick={onClose}
                    className="bg-nord4 flex h-7 w-12 items-center justify-center rounded"
                >
                    <ListIcon size={16} />
                </button>
            </div>

            {markdown !== undefined && (
                <div className="h-60">
                    <MarkdownView text={markdown} spans={relatedSpans} />
                </div>
            )}

            <div className="bg-nord4 rounded p-4">
                <div className="mb-4 flex justify-center gap-2">
                    <button
                        className="bg-nord14 flex h-7 w-12 items-center justify-center rounded"
                        onClick={() => {
                            client
                                .POST("/statements/{workspace_id}/accept", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: {
                                            statement_id: statement.current.id,
                                        },
                                    },
                                })
                                .then((stm) =>
                                    onChange(
                                        Object.fromEntries([
                                            [statement.original.id, stm.data],
                                        ]),
                                    ),
                                );
                        }}
                    >
                        <CheckIcon size={16} />
                    </button>
                    <button
                        className="bg-nord4 flex h-7 w-12 items-center justify-center rounded"
                        onClick={() => {
                            client
                                .POST("/statements/{workspace_id}/reset", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: {
                                            statement_id: statement.current.id,
                                        },
                                    },
                                })
                                .then((stm) =>
                                    onChange(
                                        Object.fromEntries([
                                            [statement.original.id, stm.data],
                                        ]),
                                    ),
                                );
                        }}
                    >
                        <RotateCcwIcon size={16} />
                    </button>
                    <button
                        className="bg-nord11 flex h-7 w-12 items-center justify-center rounded"
                        onClick={() => {
                            client
                                .POST("/statements/{workspace_id}/reject", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: {
                                            statement_id: statement.current.id,
                                        },
                                    },
                                })
                                .then((stm) =>
                                    onChange(
                                        Object.fromEntries([
                                            [statement.original.id, stm.data],
                                        ]),
                                    ),
                                );
                        }}
                    >
                        <XIcon size={16} />
                    </button>
                </div>
                <div className="grid grid-cols-3 gap-4">
                    <TextField
                        key={statement.current.subject}
                        current={statement.current.subject}
                        original={statement.original.subject}
                        edgeClassName="border-nord15"
                        onChange={(newValue: string) => {
                            client
                                .PATCH("/statements/{workspace_id}/edit", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: {
                                            statement_id: statement.current.id,
                                        },
                                    },
                                    body: { subject: newValue },
                                })
                                .then((stm) =>
                                    onChange(
                                        Object.fromEntries([
                                            [statement.original.id, stm.data],
                                        ]),
                                    ),
                                );
                        }}
                    />
                    <TextField
                        key={statement.current.predicate}
                        current={statement.current.predicate}
                        original={statement.original.predicate}
                        onChange={(newValue: string) => {
                            client
                                .PATCH("/statements/{workspace_id}/edit", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: {
                                            statement_id: statement.current.id,
                                        },
                                    },
                                    body: { predicate: newValue },
                                })
                                .then((stm) =>
                                    onChange(
                                        Object.fromEntries([
                                            [statement.original.id, stm.data],
                                        ]),
                                    ),
                                );
                        }}
                    />
                    <TextField
                        key={statement.current.object}
                        current={statement.current.object}
                        original={statement.original.object}
                        edgeClassName="border-nord13"
                        onChange={(newValue: string) => {
                            client
                                .PATCH("/statements/{workspace_id}/edit", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: {
                                            statement_id: statement.current.id,
                                        },
                                    },
                                    body: statement.current.object_is_uri
                                        ? { object_iri: newValue }
                                        : { object_value: newValue },
                                })
                                .then((stm) =>
                                    onChange(
                                        Object.fromEntries([
                                            [statement.original.id, stm.data],
                                        ]),
                                    ),
                                );
                        }}
                    />
                </div>
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-nord6 h-4"></div>
                    <div className="text-center font-mono text-sm text-nord3">
                        Confidence:{" "}
                        {(statement.current.confidence * 100).toFixed(2)}%
                    </div>
                    <div className="bg-nord6 h-4"></div>
                </div>
                <div className="grid h-80 grid-cols-2 gap-4">
                    <div className="bg-nord6 overflow-hidden rounded-tr rounded-b">
                        <EntityView
                            workspaceId={workspaceId}
                            entityId={statement.current.subject}
                            statusRefresh={`${statement.current.id}:${statement.current.curation_status}`}
                        />
                    </div>
                    <div className="bg-nord6 overflow-hidden rounded-tl rounded-b">
                        <EntityView
                            workspaceId={workspaceId}
                            entityId={statement.current.object}
                            statusRefresh={`${statement.current.id}:${statement.current.curation_status}`}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
