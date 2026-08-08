import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { apiUrl, client } from "../client";
import Spinner from "../components/Spinner";
import { TableSkeleton } from "../components/Skeleton";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import Panel from "../components/Panel";
import type {
    CurrentAndOriginalStatement,
    DocumentDetail,
    Statement,
} from "../types";
import { ArrowLeftIcon, ArrowRightIcon } from "lucide-react";
import NotFound from "./NotFound";
import MarkdownView from "../components/MarkdownView";
import Popup from "../components/Popup";
import CurationDetail from "./CurationDetail";
import {
    PACO_ACCEPTED,
    PACO_REJECTED,
    processEntityLabelWithNamespace,
} from "../ontology";

function ConfidenceBar({ percentage }: { percentage: number }) {
    return (
        <div className="h-full p-0.5 text-sm">
            <div className="relative h-full">
                <div
                    className="absolute inset-0"
                    style={{
                        width: `${100 * percentage}%`,
                        backgroundColor: `color-mix(in srgb, var(--color-nord14) ${100 * Math.pow(percentage, 4)}%, var(--color-nord11))`,
                    }}
                ></div>
                <div className="absolute inset-0 text-center">
                    {formatPercentage(percentage)}
                </div>
            </div>
        </div>
    );
}

function formatPercentage(percentage: number) {
    return (100 * percentage).toFixed(2) + "%";
}

function StatementsView({
    statements,
    page,
    setPage,
    setSelected,
    workspaceId,
    onChange,
}: {
    statements: CurrentAndOriginalStatement[];
    page: number;
    setPage: React.Dispatch<React.SetStateAction<number>>;
    setSelected: React.Dispatch<React.SetStateAction<number | undefined>>;
    workspaceId: string;
    onChange: (index: Record<string, Statement>) => void;
}) {
    const [threshold, setThreshold] = useState<number>(0);
    const [bulkAcceptInProgress, setBulkAcceptInProgress] = useState(false);

    const filteredStatements = useMemo(() => {
        return statements === undefined
            ? []
            : statements
                  .map((stm, i) => {
                      return { stm, i };
                  })
                  .filter(
                      ({ stm }) => stm.current.confidence >= threshold / 100,
                  );
    }, [statements, threshold]);

    return statements ? (
        <div className="flex min-h-0 flex-col gap-3">
            <div className="flex items-center gap-3">
                <div>Threshold</div>
                <input
                    type="range"
                    min="0"
                    max="100"
                    step="0.01"
                    value={threshold}
                    onChange={(e) =>
                        setThreshold(Number.parseFloat(e.target.value))
                    }
                />
                <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    value={threshold}
                    onChange={(e) => {
                        const value = Number.parseFloat(e.target.value);
                        if (Number.isNaN(value)) {
                            return;
                        }
                        setThreshold(Math.min(100, Math.max(0, value)));
                    }}
                    className="border-nord4 w-14 rounded border px-1 py-0.5 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                />
                <div>%</div>
                <button
                    disabled={bulkAcceptInProgress}
                    className="bg-nord8 rounded px-2 py-1"
                    onClick={() => {
                        const clone = [...filteredStatements];
                        setBulkAcceptInProgress(true);
                        client
                            .POST("/statements/{workspace_id}/bulk_accept", {
                                params: {
                                    path: { workspace_id: workspaceId },
                                },
                                body: filteredStatements.map(
                                    ({ stm }) => stm.current.id,
                                ),
                            })
                            .then((newStatements) => {
                                onChange(
                                    Object.fromEntries(
                                        newStatements.data.map((s, i) => [
                                            clone[i].stm.original.id,
                                            s,
                                        ]),
                                    ),
                                );
                                setBulkAcceptInProgress(false);
                            });
                    }}
                >
                    Bulk accept {filteredStatements.length} triples
                </button>
                <div className={!bulkAcceptInProgress && "hidden"}>
                    <Spinner />
                </div>
            </div>
            <div className="flex min-h-0 flex-col">
                <div className="bg-nord3 text-nord6 grid grid-cols-[30px_1fr_1fr_1fr_1fr] gap-5 font-bold">
                    <div className="overflow-hidden text-right text-nowrap text-ellipsis">
                        #
                    </div>
                    <div className="overflow-hidden text-nowrap text-ellipsis">
                        Subject
                    </div>
                    <div className="overflow-hidden text-nowrap text-ellipsis">
                        Predicate
                    </div>
                    <div className="overflow-hidden text-nowrap text-ellipsis">
                        Object
                    </div>
                    <div className="overflow-hidden text-nowrap text-ellipsis">
                        Confidence
                    </div>
                </div>
                <div className="flex flex-col overflow-scroll">
                    {filteredStatements
                        .filter(
                            (_, i) => i >= page * 100 && i < (page + 1) * 100,
                        )
                        .map(({ stm, i }) => {
                            return (
                                <button
                                    key={stm.original.id}
                                    className="even:bg-nord4 text-left"
                                    onClick={() => setSelected(i)}
                                >
                                    <div
                                        className={
                                            stm.current.curation_status ===
                                            PACO_ACCEPTED
                                                ? "bg-nord14/50"
                                                : stm.current
                                                        .curation_status ===
                                                    PACO_REJECTED
                                                  ? "bg-nord11/50"
                                                  : ""
                                        }
                                    >
                                        <div className="grid grid-cols-[30px_1fr_1fr_1fr_1fr] gap-5">
                                            <div className="overflow-hidden text-right text-nowrap text-ellipsis">
                                                {i + 1}
                                            </div>
                                            <div
                                                className="overflow-hidden text-nowrap text-ellipsis"
                                                title={stm.current.subject}
                                            >
                                                {processEntityLabelWithNamespace(
                                                    stm.current.subject,
                                                )}
                                            </div>
                                            <div className="overflow-hidden text-nowrap text-ellipsis">
                                                {stm.current.predicate}
                                            </div>
                                            <div
                                                className="overflow-hidden text-nowrap text-ellipsis"
                                                title={stm.current.object}
                                            >
                                                {processEntityLabelWithNamespace(
                                                    stm.current.object,
                                                )}
                                            </div>
                                            <div className="overflow-hidden text-nowrap text-ellipsis">
                                                <ConfidenceBar
                                                    percentage={
                                                        stm.current.confidence
                                                    }
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </button>
                            );
                        })}
                </div>
            </div>
            <div className="flex justify-center gap-2">
                <button
                    className="bg-nord4"
                    onClick={() => {
                        if (page > 0) setPage(page - 1);
                    }}
                >
                    <ArrowLeftIcon />
                </button>
                <div>
                    {page + 1} / {Math.ceil(statements.length / 100)}
                </div>
                <button
                    className="bg-nord4"
                    onClick={() => {
                        if (page < Math.ceil(statements.length / 100) - 1)
                            setPage(page + 1);
                    }}
                >
                    <ArrowRightIcon />
                </button>
            </div>
        </div>
    ) : (
        <TableSkeleton
            gridColsClassName="grid-cols-[30px_1fr_1fr_1fr_1fr]"
            columns={5}
            rows={20}
        />
    );
}

export default function CurationPage() {
    const [searchParams] = useSearchParams();
    const location = useLocation();
    const [selected, setSelected] = useState<number | undefined>(undefined);

    // load filename immediately if known from previous page, to avoid spinner when statements request is handled first by backend
    const filenameFromState = (location.state as { filename?: string } | null)
        ?.filename;

    const [doc, setDoc] = useState<DocumentDetail | undefined>(undefined);

    const [statements, setStatements] = useState<
        CurrentAndOriginalStatement[] | undefined
    >(undefined);

    const tabs = [
        {
            value: "triples",
            label: "Statements",
        },
        {
            value: "document",
            label: "Document",
        },
    ] as const;

    const [tab, setTab] = useState<(typeof tabs)[number]["value"]>("triples");
    const [page, setPage] = useState<number>(0);

    const wsId = searchParams.get("ws");
    const docId = searchParams.get("doc");

    const reloadStatements = useCallback(() => {
        if (docId === null) {
            client
                .GET("/graph/{workspace_id}/deduplication", {
                    params: { path: { workspace_id: wsId } },
                })
                .then((statements) => {
                    if (statements.data !== null) {
                        setStatements(statements.data);
                    }
                });
        } else {
            client
                .GET("/documents/{document_id}", {
                    params: { path: { document_id: docId } },
                })
                .then((doc) => {
                    if (doc.data !== null) {
                        setDoc(doc.data);
                    }
                });
            client
                .GET("/documents/{document_id}/statements", {
                    params: { path: { document_id: docId } },
                })
                .then((statements) => {
                    if (statements.data !== null) {
                        setStatements(statements.data);
                    }
                    setPage(0);
                });
        }
    }, [wsId, docId]);

    useEffect(() => {
        reloadStatements();
    }, [reloadStatements]);

    if (wsId === null) {
        return <NotFound />;
    }

    function updateStatements(update: Record<string, Statement>) {
        setStatements((prev) =>
            prev.map((stm, i) =>
                stm.original.id in update
                    ? {
                          original: prev[i].original,
                          current: update[stm.original.id],
                      }
                    : stm,
            ),
        );
    }

    return (
        <>
            <Panel className="flex h-full min-h-160 w-full flex-col">
                <div className="relative mb-4">
                    <Link
                        to={`/workspace?ws=${wsId}`}
                        className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                    >
                        <ArrowLeftIcon size={16} />
                    </Link>
                    <h1 className="text-center text-xl">
                        {docId === null ? (
                            <>Deduplication</>
                        ) : (
                            <>
                                Document{" "}
                                {doc?.filename ??
                                    filenameFromState ?? <Spinner />}
                            </>
                        )}
                    </h1>
                    {docId === null &&
                        (statements?.some(
                            (s) => s.current.curation_status === PACO_ACCEPTED,
                        ) ? (
                            <div className="bg-nord4 absolute top-0 right-0 flex h-full items-center gap-2 rounded px-3 text-sm">
                                <span>Export merged graph:</span>
                                <a
                                    className="underline"
                                    href={apiUrl(
                                        `/graph/${wsId}/deduplication/export?format=turtle`,
                                    )}
                                >
                                    Turtle
                                </a>
                                <a
                                    className="underline"
                                    href={apiUrl(
                                        `/graph/${wsId}/deduplication/export?format=json-ld`,
                                    )}
                                >
                                    JSON-LD
                                </a>
                            </div>
                        ) : (
                            <div
                                className="bg-nord4 absolute top-0 right-0 flex h-full cursor-not-allowed items-center gap-2 rounded px-3 text-sm opacity-40"
                                title="No owl:sameAs statements have been accepted yet"
                                aria-disabled="true"
                            >
                                <span>Export merged graph</span>
                            </div>
                        ))}
                </div>

                <div className="mb-4 flex gap-4">
                    {tabs.map((t) => {
                        if (t.value === "document" && docId === null) {
                            return <Fragment key={t.value} />;
                        } else {
                            return (
                                <button
                                    className={`rounded px-2 py-1 ${t.value === tab ? "bg-nord8" : "bg-nord4"}`}
                                    key={t.value}
                                    onClick={() => setTab(t.value)}
                                >
                                    {t.label}
                                </button>
                            );
                        }
                    })}
                </div>

                {(tab === "triples" && (
                    <StatementsView
                        statements={statements}
                        page={page}
                        setPage={setPage}
                        setSelected={setSelected}
                        workspaceId={wsId}
                        onChange={(update) => updateStatements(update)}
                    />
                )) ||
                    (tab === "document" && docId !== null && (
                        <>
                            {doc ? (
                                <MarkdownView text={doc.markdown} spans={[]} />
                            ) : (
                                <Spinner />
                            )}
                        </>
                    ))}

                <div
                    className={`h-full min-h-0 flex-1 ${docId === null ? "" : "grid grid-cols-[1fr_auto_1fr] gap-4"}`}
                ></div>
            </Panel>
            {statements === undefined ||
            selected >= statements.length ||
            statements[selected] === undefined ? (
                <></>
            ) : (
                <Popup show={true}>
                    <CurationDetail
                        onClose={() => setSelected(undefined)}
                        onNext={() => setSelected(selected + 1)}
                        onPrevious={() => setSelected(selected - 1)}
                        onChange={(update) => updateStatements(update)}
                        index={selected}
                        total={statements.length}
                        statement={statements[selected]}
                        workspaceId={wsId}
                        markdown={doc?.markdown}
                        docId={docId}
                    />
                </Popup>
            )}
        </>
    );
}
