import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Root from "../components/Root";
import { client } from "../client";
import { useEffect, useState } from "react";
import {
    ArrowLeftIcon,
    EditIcon,
    FilePlusIcon,
    MergeIcon,
    SearchIcon,
    ShareIcon,
    TrashIcon,
} from "lucide-react";
import type { Document } from "../types";
import Spinner from "../components/Spinner";
import Panel from "../components/Panel";
import NotFound from "./NotFound";

export default function WorkspacePage() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    const [ws, setWs] = useState<{ id: string; name: string } | undefined>(
        undefined,
    );
    const [docs, setDocs] = useState<Document[]>(undefined);

    const [docStatus, setDocStatus] = useState<{ [id: string]: string }>({});

    const wsId = searchParams.get("ws");

    useEffect(() => {
        if (wsId === null) return;
        client
            .GET("/workspaces/{workspace_id}", {
                params: { path: { workspace_id: wsId } },
            })
            .then((res) => setWs(res.data));
    }, [wsId]);

    useEffect(() => {
        if (wsId === null) return;
        client
            .GET("/documents/", {
                params: { query: { workspace_id: wsId } },
            })
            .then((res) => setDocs(res.data));
    }, [wsId]);

    useEffect(() => {
        function updateDocStatus() {
            client
                .GET("/extraction/{workspace_id}", {
                    params: { path: { workspace_id: wsId } },
                })
                .then((res) => {
                    if (!res.data) return;
                    const statusMap = {};
                    for (const entry of res.data) {
                        statusMap[entry.document_id] = entry.status;
                    }
                    setDocStatus(statusMap);
                });
        }
        updateDocStatus();
        const interval = setInterval(updateDocStatus, 1000);
        return () => clearInterval(interval);
    }, [wsId]);

    if (wsId === null) {
        return <NotFound />;
    }

    return (
        <Root>
            <Panel className="flex w-160 flex-col gap-2">
                <div className="relative mb-4">
                    <Link
                        to="/workspaces"
                        className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                    >
                        <ArrowLeftIcon size={16} />
                    </Link>
                    <h1 className="text-center text-xl">
                        {ws ? <>Workspace {ws.name}</> : <Spinner />}
                    </h1>
                </div>

                {docs === undefined ? (
                    <Spinner />
                ) : docs.length === 0 ? (
                    <div className="text-center italic">
                        No documents have been uploaded yet.
                    </div>
                ) : (
                    <div className="grid grid-cols-4 gap-2">
                        <div>Document</div>
                        <div>Extracted triples</div>
                        <div>Pending review</div>
                        <div></div>
                        {docs.map((d) => (
                            <div key={d.id} className="contents">
                                <div>{d.filename}</div>
                                {docStatus[d.id] === "done" ? (
                                    <>
                                        <div>{d.extracted_triples}</div>
                                        <div>{d.pending_triples}</div>
                                    </>
                                ) : (
                                    <div
                                        className={`col-span-2 text-center ${
                                            docStatus[d.id] === "failed"
                                                ? "stripes-failed"
                                                : "stripes-running"
                                        }`}
                                    >
                                        {docStatus[d.id]}
                                    </div>
                                )}
                                <div className="flex gap-2">
                                    <button
                                        className="bg-nord8 h-7 rounded px-2"
                                        onClick={() => {
                                            navigate(
                                                `/curation?ws=${wsId}&doc=${d.id}`,
                                            );
                                        }}
                                    >
                                        <EditIcon size={16} />
                                    </button>
                                    <button
                                        className="bg-nord8 h-7 rounded px-2"
                                        onClick={() => {}}
                                    >
                                        <ShareIcon size={16} />
                                    </button>
                                    <button
                                        className="bg-nord11 h-7 rounded px-2"
                                        onClick={() => {
                                            client.DELETE(
                                                "/documents/{document_id}",
                                                {
                                                    params: {
                                                        path: {
                                                            document_id: d.id,
                                                        },
                                                    },
                                                },
                                            );
                                        }}
                                    >
                                        <TrashIcon size={16} />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                <div className="mt-4 flex justify-center gap-4">
                    <Link
                        to={`/upload?ws=${wsId}`}
                        className="bg-nord8 relative flex h-24 w-32 items-center justify-center rounded px-2"
                    >
                        <FilePlusIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Start new run</div>
                    </Link>
                    <Link
                        to={`/curation?ws=${wsId}`}
                        className="bg-nord8 relative flex h-24 w-32 items-center justify-center rounded px-2"
                    >
                        <MergeIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Deduplication</div>
                    </Link>
                    <button className="bg-nord8 relative h-24 w-32 rounded px-2">
                        <SearchIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Queries</div>
                    </button>
                    <button className="bg-nord8 relative h-24 w-32 rounded px-2">
                        <ShareIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Export</div>
                    </button>
                </div>
            </Panel>
        </Root>
    );
}
