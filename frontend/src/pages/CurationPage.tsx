import { Fragment, useCallback, useEffect, useState } from "react";
import { client } from "../client";
import Spinner from "../components/Spinner";
import { Link, useSearchParams } from "react-router-dom";
import Panel from "../components/Panel";
import type { CurrentAndOriginalStatement, DocumentDetail } from "../types";
import { ArrowLeftIcon, ArrowRightIcon } from "lucide-react";
import NotFound from "./NotFound";
import MarkdownView from "../components/MarkdownView";
import Popup from "../components/Popup";
import CurationDetail from "./CurationDetail";
import { PACO_ACCEPTED, PACO_REJECTED } from "../ontology";

function StatementsView({
    statements,
    page,
    setPage,
    setSelected,
}: {
    statements: CurrentAndOriginalStatement[];
    page: number;
    setPage: React.Dispatch<React.SetStateAction<number>>;
    setSelected: React.Dispatch<React.SetStateAction<number | undefined>>;
}) {
    return statements ? (
        <div className="flex min-h-0 flex-col gap-3">
            <div className="flex flex-col overflow-scroll">
                {statements
                    .map((stm, i) => {
                        return { stm, i };
                    })
                    .filter(({ i }) => i >= page * 100 && i < (page + 1) * 100)
                    .map(({ stm, i }) => {
                        return (
                            <button
                                key={stm.original.id}
                                className="even:bg-nord4"
                                onClick={() => setSelected(i)}
                            >
                                <div
                                    className={
                                        stm.current.curation_status ===
                                        PACO_ACCEPTED
                                            ? "bg-nord14/50"
                                            : stm.current.curation_status ===
                                                PACO_REJECTED
                                              ? "bg-nord11/50"
                                              : ""
                                    }
                                >
                                    <div className="grid grid-cols-[30px_1fr_1fr_1fr] gap-5">
                                        <div className="overflow-hidden text-right text-nowrap text-ellipsis">
                                            {i + 1}
                                        </div>
                                        <div className="overflow-hidden text-nowrap text-ellipsis">
                                            {stm.current.subject}
                                        </div>
                                        <div className="overflow-hidden text-nowrap text-ellipsis">
                                            {stm.current.predicate}
                                        </div>
                                        <div className="overflow-hidden text-nowrap text-ellipsis">
                                            {stm.current.object}
                                        </div>
                                    </div>
                                </div>
                            </button>
                        );
                    })}
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
        <Spinner />
    );
}

export default function CurationPage() {
    const [searchParams] = useSearchParams();
    const [selected, setSelected] = useState<number | undefined>(undefined);

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
                        console.log(statements.data);
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
                            <>Document {doc ? doc.filename : <Spinner />}</>
                        )}
                    </h1>
                </div>

                <div className="mb-4 flex gap-4">
                    {tabs.map((t) => {
                        if (t.value === "document" && docId === null) {
                            return <Fragment key={t.value} />;
                        } else {
                            return (
                                <button
                                    className={`rounded p-2 ${t.value === tab ? "bg-nord8" : "bg-nord4"}`}
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
                    />
                )) ||
                    (tab === "document" && docId !== null && (
                        <>
                            {doc ? (
                                <MarkdownView
                                    text={doc.markdown}
                                    spans={[]}
                                />
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
                        onChange={(i) => {
                            client
                                .GET(
                                    "/statements/{workspace_id}/statements/{statement_id}/current",
                                    {
                                        params: {
                                            path: {
                                                workspace_id: wsId,
                                                statement_id:
                                                    statements[i].current.id,
                                            },
                                        },
                                    },
                                )
                                .then((newStatement) => {
                                    setStatements(
                                        statements.map((stm, j) =>
                                            i === j
                                                ? {
                                                      original:
                                                          statements[i]
                                                              .original,
                                                      current:
                                                          newStatement.data,
                                                  }
                                                : stm,
                                        ),
                                    );
                                });
                        }}
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
