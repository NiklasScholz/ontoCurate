import {
    ArrowLeftIcon,
    ArrowRightIcon,
    CheckIcon,
    EditIcon,
    ListIcon,
    RotateCcwIcon,
    XIcon,
} from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { client } from "../client.ts";
import Spinner from "../components/Spinner.tsx";
import type { Statement } from "../types.ts";
import MarkdownView from "../components/MarkdownView.tsx";

type Neighborhood = {
    incoming: { predicate: string; subject: string }[];
    outgoing: { predicate: string; object: string }[];
};

function LocalGraphView({
    center,
    incoming,
    outgoing,
}: {
    center: string;
} & Neighborhood) {
    const styles = getComputedStyle(document.documentElement);
    const nord0 = styles.getPropertyValue("--color-nord0");
    const nord4 = styles.getPropertyValue("--color-nord4");
    const nord8 = styles.getPropertyValue("--color-nord8");

    function calcY(i: number, n: number): number {
        return (i + 0.5) * (500 / n);
    }

    function text(s: string): string {
        const url = "http://example.org/scholarly-metadata-ontology";
        return s.startsWith(url) ? s.substring(url.length) : s;
    }

    return (
        <svg viewBox="0 0 800 500" className="h-full w-full">
            {incoming.map(({ predicate, subject }, i) => {
                return (
                    <Fragment key={i}>
                        <line
                            x1="100"
                            y1={calcY(i, incoming.length)}
                            x2="400"
                            y2="250"
                            stroke={nord4}
                            strokeWidth="5"
                        />
                        <circle
                            r="30"
                            cx="100"
                            cy={calcY(i, incoming.length)}
                            fill={nord4}
                        />
                        <text
                            x="250"
                            y={(calcY(i, incoming.length) + 250) / 2}
                            textAnchor="middle"
                            dominantBaseline="middle"
                            fill={nord0}
                            fontSize="18"
                        >
                            {text(predicate)}
                        </text>
                        <text
                            x="100"
                            y={calcY(i, incoming.length)}
                            textAnchor="middle"
                            dominantBaseline="middle"
                            fill={nord0}
                            fontSize="18"
                        >
                            {text(subject)}
                        </text>
                    </Fragment>
                );
            })}
            {outgoing.map(({ predicate, object }, i) => {
                return (
                    <Fragment key={i}>
                        <line
                            x1="400"
                            y1="250"
                            x2="700"
                            y2={calcY(i, outgoing.length)}
                            stroke={nord4}
                            strokeWidth="5"
                        />
                        <circle
                            r="30"
                            cx="700"
                            cy={calcY(i, outgoing.length)}
                            fill={nord4}
                        />
                        <text
                            x="550"
                            y={(calcY(i, outgoing.length) + 250) / 2}
                            textAnchor="middle"
                            dominantBaseline="middle"
                            fill={nord0}
                            fontSize="18"
                        >
                            {text(predicate)}
                        </text>
                        <text
                            x="700"
                            y={calcY(i, outgoing.length)}
                            textAnchor="middle"
                            dominantBaseline="middle"
                            fill={nord0}
                            fontSize="18"
                        >
                            {text(object)}
                        </text>
                    </Fragment>
                );
            })}
            <circle r="30" cx="400" cy="250" fill={nord8} />
            <text
                x="400"
                y="250"
                textAnchor="middle"
                dominantBaseline="middle"
                fill={nord0}
                fontSize="18"
            >
                {text(center)}
            </text>
        </svg>
    );
}

function EntityView({
    workspaceId,
    entityId,
}: {
    workspaceId: string;
    entityId: string;
}) {
    const [neighborhood, setNeighborhood] = useState<Neighborhood | undefined>(
        undefined,
    );

    useEffect(() => {
        client
            .GET("/graph/{workspace_id}/neighborhood", {
                params: {
                    path: { workspace_id: workspaceId },
                    query: { entity_id: entityId },
                },
            })
            .then((res) => {
                setNeighborhood(res.data);
            });
    }, [workspaceId, entityId]);

    return neighborhood ? (
        <div>
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
}: {
    onClose: () => void;
    onPrevious: () => void;
    onNext: () => void;
    onChange: (id: string) => void;
    workspaceId: string;
    markdown: string;
    index: number;
    total: number;
    statement: Statement;
}) {
    return (
        <div className="bg-nord6 flex h-full w-full max-w-7xl flex-col gap-2 rounded p-4 shadow-xl">
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

            <div
                className={`h-60 ${
                    statement.text_span_start === null ||
                    statement.text_span_end === null
                        ? "opacity-50"
                        : ""
                }`}
            >
                <MarkdownView
                    text={markdown}
                    span={
                        statement.text_span_start === null ||
                        statement.text_span_end === null
                            ? undefined
                            : {
                                  start: statement.text_span_start,
                                  end: statement.text_span_end,
                              }
                    }
                />
            </div>
            <div className="bg-nord4 rounded p-4">
                <div className="mb-4 flex justify-center gap-2">
                    <button
                        className="bg-nord14 flex h-7 w-12 items-center justify-center rounded"
                        onClick={() => {
                            client
                                .POST("/statements/{workspace_id}/accept", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: { statement_id: statement.id },
                                    },
                                })
                                .then((res) => onChange(res.data.id));
                        }}
                    >
                        <CheckIcon size={16} />
                    </button>
                    <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                        <RotateCcwIcon size={16} />
                    </button>
                    <button
                        className="bg-nord11 flex h-7 w-12 items-center justify-center rounded"
                        onClick={() => {
                            client
                                .POST("/statements/{workspace_id}/reject", {
                                    params: {
                                        path: { workspace_id: workspaceId },
                                        query: { statement_id: statement.id },
                                    },
                                })
                                .then((res) => onChange(res.data.id));
                        }}
                    >
                        <XIcon size={16} />
                    </button>
                </div>
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-nord6 flex h-40 flex-col justify-between gap-2 rounded-t p-2">
                        <div className="font-mono text-sm wrap-anywhere">
                            {statement.subject}
                        </div>
                        <div className="flex justify-center gap-2">
                            <button className="bg-nord8 flex h-7 w-12 items-center justify-center rounded">
                                <EditIcon size={16} />
                            </button>
                            <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                                <RotateCcwIcon size={16} />
                            </button>
                        </div>
                    </div>
                    <div className="bg-nord6 flex h-40 flex-col justify-between gap-2 rounded p-2">
                        <div className="font-mono text-sm wrap-anywhere">
                            {statement.predicate}
                        </div>
                        <div className="flex justify-center gap-2">
                            <button className="bg-nord8 flex h-7 w-12 items-center justify-center rounded">
                                <EditIcon size={16} />
                            </button>
                            <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                                <RotateCcwIcon size={16} />
                            </button>
                        </div>
                    </div>
                    <div className="bg-nord6 flex h-40 flex-col justify-between gap-2 rounded-t p-2">
                        <div className="font-mono text-sm wrap-anywhere">
                            {statement.object}
                        </div>
                        <div className="flex justify-center gap-2">
                            <button className="bg-nord8 flex h-7 w-12 items-center justify-center rounded">
                                <EditIcon size={16} />
                            </button>
                            <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                                <RotateCcwIcon size={16} />
                            </button>
                        </div>
                    </div>
                </div>
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-nord6 h-4"></div>
                    <div></div>
                    <div className="bg-nord6 h-4"></div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-nord6 rounded-tr rounded-b">
                        <EntityView
                            workspaceId={workspaceId}
                            entityId={statement.subject}
                        />
                    </div>
                    <div className="bg-nord6 rounded-tl rounded-b">
                        <EntityView
                            workspaceId={workspaceId}
                            entityId={statement.object}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
