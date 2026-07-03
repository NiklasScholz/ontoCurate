import { useEffect, useState } from "react";
import { client } from "../client";
import Spinner from "../components/Spinner";
import { Link, useSearchParams } from "react-router-dom";
import Root from "../components/Root";
import Panel from "../components/Panel";
import type { DocumentDetail, Statement } from "../types";
import { ArrowLeftIcon } from "lucide-react";
import NotFound from "./NotFound";
import MarkdownView from "../components/MarkdownView";

export default function CurationOverviewPage() {
    const [searchParams] = useSearchParams();
    const [selected, setSelected] = useState<number | undefined>(undefined);

    const [doc, setDoc] = useState<DocumentDetail | undefined>(undefined);

    const [statements, setStatements] = useState<Statement[] | undefined>(
        undefined,
    );

    const wsId = searchParams.get("ws");
    const docId = searchParams.get("doc");

    useEffect(() => {
        if (docId === null) return;
        client
            .GET("/documents/{document_id}", {
                params: { path: { document_id: docId } },
            })
            .then((doc) => {
                if (doc.data !== null) {
                    setDoc(doc.data);
                }
            });
    }, [docId]);

    useEffect(() => {
        if (docId === null) return;
        client
            .GET("/documents/{document_id}/statements", {
                params: { path: { document_id: docId } },
            })
            .then((statements) => {
                console.log(statements);
                if (statements.data !== null) {
                    setStatements(statements.data);
                }
            });
    }, [docId]);

    if (wsId === null || docId === null) {
        return <NotFound />;
    }

    return (
        <Root>
            <Panel className="flex h-full min-h-160 min-w-160 flex-col">
                <div className="relative mb-4">
                    <Link
                        to={`/workspace?ws=${wsId}`}
                        className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                    >
                        <ArrowLeftIcon size={16} />
                    </Link>
                    <h1 className="text-center text-xl">
                        Document {doc ? doc.filename : <Spinner />}
                    </h1>
                </div>

                <div className="grid min-h-0 flex-1 grid-cols-[1fr_auto_1fr] gap-4">
                    {statements ? (
                        <div className="flex h-full flex-col overflow-scroll">
                            {statements
                                .filter((_stm, i) => i < 100)
                                .map((stm, i) => {
                                    return (
                                        <button
                                            className="even:bg-nord4"
                                            onClick={() => setSelected(i)}
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
                                        </button>
                                    );
                                })}
                        </div>
                    ) : (
                        <Spinner />
                    )}
                    <div className="bg-nord4 h-full w-0.5"></div>
                    {doc ? (
                        <MarkdownView
                            text={doc.markdown}
                            span={
                                selected === undefined
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
                </div>
            </Panel>
        </Root>
    );
}
