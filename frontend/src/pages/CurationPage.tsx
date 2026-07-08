import { useCallback, useEffect, useState } from "react";
import { client } from "../client";
import Spinner from "../components/Spinner";
import { Link, useSearchParams } from "react-router-dom";
import Panel from "../components/Panel";
import type { DocumentDetail, Statement } from "../types";
import { ArrowLeftIcon, ArrowRightIcon } from "lucide-react";
import NotFound from "./NotFound";
import MarkdownView from "../components/MarkdownView";
import Popup from "../components/Popup";
import CurationDetail from "./CurationDetail";

export default function CurationOverviewPage() {
    const [searchParams] = useSearchParams();
    const [selected, setSelected] = useState<number | undefined>(undefined);

    const [doc, setDoc] = useState<DocumentDetail | undefined>(undefined);

    const [statements, setStatements] = useState<Statement[] | undefined>(
        undefined,
    );

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

    return (
        <>
            <Panel className="flex h-full min-h-160 min-w-160 flex-col">
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

                <div
                    className={`h-full min-h-0 flex-1 ${docId === null ? "" : "grid grid-cols-[1fr_auto_1fr] gap-4"}`}
                >
                    {statements ? (
                        <div className="flex min-h-0 flex-col gap-3">
                            <div className="flex flex-col overflow-scroll">
                                {statements
                                    .filter(
                                        (_stm, i) =>
                                            i >= page * 100 &&
                                            i < (page + 1) * 100,
                                    )
                                    .map((stm, i) => {
                                        return (
                                            <button
                                                key={stm.id}
                                                className="even:bg-nord4"
                                                onClick={() => setSelected(i)}
                                            >
                                                <div
                                                    className={
                                                        stm.curation_status ===
                                                        "accepted"
                                                            ? "bg-nord14/50"
                                                            : stm.curation_status ===
                                                                "rejected"
                                                              ? "bg-nord11/50"
                                                              : stm.curation_status ===
                                                                  "edited"
                                                                ? "bg-nord13/50"
                                                                : ""
                                                    }
                                                >
                                                    <div className="grid grid-cols-3">
                                                        <div className="overflow-hidden text-nowrap text-ellipsis">
                                                            {stm.subject}
                                                        </div>
                                                        <div className="overflow-hidden text-nowrap text-ellipsis">
                                                            {stm.predicate}
                                                        </div>
                                                        <div className="overflow-hidden text-nowrap text-ellipsis">
                                                            {stm.object}
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
                                    {page + 1} /{" "}
                                    {Math.ceil(statements.length / 100)}
                                </div>
                                <button
                                    className="bg-nord4"
                                    onClick={() => {
                                        if (
                                            page <
                                            Math.ceil(statements.length / 100) -
                                                1
                                        )
                                            setPage(page + 1);
                                    }}
                                >
                                    <ArrowRightIcon />
                                </button>
                            </div>
                        </div>
                    ) : (
                        <Spinner />
                    )}
                    {docId === null ? (
                        <></>
                    ) : (
                        <>
                            <div className="bg-nord4 h-full w-0.5"></div>
                            {doc ? (
                                <MarkdownView
                                    text={doc.markdown}
                                    span={
                                        selected === undefined ||
                                        statements[selected].text_span_start ===
                                            null ||
                                        statements[selected].text_span_end ===
                                            null
                                            ? undefined
                                            : {
                                                  start: statements[selected]
                                                      .text_span_start,
                                                  end: statements[selected]
                                                      .text_span_end,
                                              }
                                    }
                                />
                            ) : (
                                <Spinner />
                            )}
                        </>
                    )}
                </div>
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
                        onChange={() => reloadStatements()}
                        index={selected}
                        total={statements.length}
                        statement={statements[selected]}
                        workspaceId={wsId}
                        markdown={doc.markdown}
                    />
                </Popup>
            )}
        </>
    );
}
