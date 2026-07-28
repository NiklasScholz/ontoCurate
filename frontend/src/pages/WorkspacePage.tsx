import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiUrl, client } from "../client";
import { useEffect, useState } from "react";
import {
    ArrowLeftIcon,
    EditIcon,
    FilePlusIcon,
    MergeIcon,
    RefreshCwIcon,
    SearchIcon,
    ShareIcon,
    TrashIcon,
} from "lucide-react";
import type { Document } from "../types";
import Spinner from "../components/Spinner";
import Panel from "../components/Panel";
import NotFound from "./NotFound";
import {
    type ExistingMember,
    type PendingInvite,
} from "../components/InviteMembersPanel";
import InviteMembersSection from "../components/InviteMembersPanel";

// Shorter names so that it fits into the colum without extra line
const SHORT_TASK_NAME: Record<string, string> = {
    "Inner Document Alignment": "Alignment",
    "Cross-Document Alignment": "Alignment",
    "Wikidata Lookup": "Lookup",
};

function formatDocStatus(
    status: string | undefined,
    taskName: string | undefined,
): string {
    if (!status) return "";
    if (taskName) {
        return `${status}: ${SHORT_TASK_NAME[taskName] ?? taskName}`;
    }
    return status;
}

export default function WorkspacePage() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    const [ws, setWs] = useState<
        { id: string; name: string; role: string } | undefined
    >(undefined);

    const [docs, setDocs] = useState<Document[]>(undefined);
    const [docRunInfo, setDocRunInfo] = useState<{
        [id: string]: { status: string; taskName: string; runId: string };
    }>({});
    const [members, setMembers] = useState<ExistingMember[]>([]);
    const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);
    const [inviteError, setInviteError] = useState<string | null>(null);
    const [docActionError, setDocActionError] = useState<string | null>(null);
    const [dedupCounts, setDedupCounts] = useState({ total: 0, pending: 0 });

    const fetchMembers = (id: string) => {
        client
            .GET("/workspaces/{workspace_id}/members", {
                params: { path: { workspace_id: id } },
            })
            .then(({ data }) => {
                if (data) setMembers(data);
            });
    };

    const handleInviteChange = async (updated: PendingInvite[]) => {
        if (updated.length <= pendingInvites.length) {
            setPendingInvites(updated);
            return;
        }

        const newest = updated[updated.length - 1];
        const { error } = await client.POST(
            "/workspaces/{workspace_id}/members",
            {
                params: { path: { workspace_id: ws.id } },
                body: { user_info: newest.user_info, role: newest.role },
            },
        );

        if (error) {
            setInviteError(
                (error as { detail?: string }).detail ?? "Failed to add member",
            );
        } else {
            setInviteError(null);
            setPendingInvites([]);
            fetchMembers(ws.id);
        }
    };

    const handleRemoveMember = async (member: ExistingMember) => {
        const { error } = await client.DELETE(
            "/workspaces/{workspace_id}/members/{user_id}",
            {
                params: { path: { workspace_id: ws.id, user_id: member.id } },
            },
        );

        if (error) {
            setInviteError(
                (error as { detail?: string }).detail ??
                    "Failed to remove member",
            );
        } else {
            setInviteError(null);
            fetchMembers(ws.id);
        }
    };

    const hasTriples =
        docs !== undefined &&
        docs.some((d) => (d.extracted_triples ?? 0) > 0);

    const wsId = searchParams.get("ws");

    useEffect(() => {
        if (wsId === null) return;
        client
            .GET("/workspaces/{workspace_id}", {
                params: { path: { workspace_id: wsId } },
            })
            .then((res) => setWs(res.data));
    }, [wsId]);

    function updateDocStatus() {
        if (wsId === null) return;
        client
            .GET("/extraction/{workspace_id}", {
                params: { path: { workspace_id: wsId } },
            })
            .then((res) => {
                if (!res.data) return;
                const infoMap = {};
                for (const entry of res.data) {
                    infoMap[entry.document_id] = {
                        status: entry.status,
                        taskName: entry.task_name,
                        runId: entry.run_id,
                    };
                }
                setDocRunInfo(infoMap);
                client
                    .GET("/documents/", {
                        params: { query: { workspace_id: wsId } },
                    })
                    .then((res) => setDocs(res.data));
            });
    }

    useEffect(() => {
        updateDocStatus();
        const interval = setInterval(updateDocStatus, 10000);
        return () => clearInterval(interval);
    }, [wsId]);

    useEffect(() => {
        if (wsId === null) return;
        const fetchDedupCount = () => {
            client
                .GET("/graph/{workspace_id}/deduplication/count", {
                    params: { path: { workspace_id: wsId } },
                })
                .then((res) =>
                    setDedupCounts({
                        total: res.data?.total_count ?? 0,
                        pending: res.data?.pending_count ?? 0,
                    }),
                );
        };
        fetchDedupCount();
        const interval = setInterval(fetchDedupCount, 10000);
        return () => clearInterval(interval);
    }, [wsId]);

    useEffect(() => {
        if (!ws || ws.role !== "owner") return;
        fetchMembers(ws.id);
    }, [ws]);

    const handleDeleteDocument = async (doc: Document) => {
        if (
            !window.confirm(
                `Delete "${doc.filename}"? This cannot be undone.`,
            )
        ) {
            return;
        }
        const { error } = await client.DELETE("/documents/{document_id}", {
            params: { path: { document_id: doc.id } },
        });
        if (error) {
            setDocActionError(
                (error as { detail?: string }).detail ??
                    "Failed to delete document",
            );
            return;
        }
        setDocActionError(null);
        setDocs((prev) => prev.filter((d) => d.id !== doc.id));
        setDocRunInfo((prev) => {
            const next = { ...prev };
            delete next[doc.id];
            return next;
        });
    };

    const handleRetryDocument = async (doc: Document) => {
        const runId = docRunInfo[doc.id]?.runId;
        if (!runId) return;
        const { error } = await client.POST(
            "/extraction/{run_id}/documents/{document_id}/retry",
            {
                params: { path: { run_id: runId, document_id: doc.id } },
            },
        );
        if (error) {
            setDocActionError(
                (error as { detail?: string }).detail ??
                    "Failed to retry document",
            );
            return;
        }
        setDocActionError(null);
        updateDocStatus();
    };

    if (wsId === null) {
        return <NotFound />;
    }

    return (
        <Panel className="flex w-200 flex-col gap-2">
            <div className="relative mb-4">
                <Link
                    to="/workspaces"
                    className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                >
                    <ArrowLeftIcon size={16} />
                </Link>
                <h1 className="text-center text-xl">
                    {ws ? <>Workspace - {ws.name}</> : <Spinner />}
                </h1>
            </div>

            {docActionError && (
                <p className="text-nord11 text-center text-sm">
                    {docActionError}
                </p>
            )}

            {docs === undefined ? (
                <Spinner />
            ) : docs.length === 0 ? (
                <div className="text-center italic">
                    No documents have been uploaded yet.
                </div>
            ) : (
                <div className="grid max-h-[40vh] grid-cols-[auto_auto_auto_auto_auto] items-center gap-x-6 gap-y-2 overflow-y-auto">
                    <div>Document</div>
                    <div>Uploaded</div>
                    {docs.some((d) => docRunInfo[d.id]?.status === "Done") ? (
                        <>
                            <div>Extracted triples</div>
                            <div>Pending review</div>
                        </>
                    ) : (
                        <>
                            <div></div>
                            <div></div>
                        </>
                    )}
                    <div></div>
                    {docs.map((d) => (
                        <div key={d.id} className="contents">
                            <div>
                                {d.file_type === "pdf" ? (
                                    <a
                                        className="underline"
                                        href={apiUrl(`/documents/${d.id}/pdf`)}
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        {d.filename}
                                    </a>
                                ) : d.file_type === "markdown" ? (
                                    <a
                                        className="underline"
                                        href={apiUrl(`/documents/${d.id}/markdown`)}
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        {d.filename}
                                    </a>
                                ) : (
                                    d.filename
                                )}
                            </div>
                            <div>{new Date(d.created_at).toLocaleString()}</div>
                            {docRunInfo[d.id]?.status === "Done" ? (
                                <>
                                    <div>{d.extracted_triples}</div>
                                    <div>{d.pending_triples}</div>
                                </>
                            ) : (
                                <div
                                    className={`col-span-2 text-center ${
                                        docRunInfo[d.id]?.status === "Failed"
                                            ? "stripes-failed"
                                            : "stripes-running"
                                    }`}
                                >
                                    {formatDocStatus(
                                        docRunInfo[d.id]?.status,
                                        docRunInfo[d.id]?.taskName,
                                    )}
                                </div>
                            )}
                            <div className="flex gap-2">
                                <button
                                    className="bg-nord8 h-7 rounded px-2"
                                    title="Edit"
                                    aria-label="Edit"
                                    onClick={() => {
                                        navigate(
                                            `/curation?ws=${wsId}&doc=${d.id}`,
                                            { state: { filename: d.filename } },
                                        );
                                    }}
                                >
                                    <EditIcon size={16} />
                                </button>
                                <button
                                    className="bg-nord8 h-7 rounded px-2"
                                    title="Export"
                                    aria-label="Export"
                                    onClick={() => {}}
                                >
                                    <ShareIcon size={16} />
                                </button>
                                {docRunInfo[d.id]?.status === "Failed" && (
                                    <button
                                        className="bg-nord8 h-7 rounded px-2"
                                        title="Retry"
                                        aria-label="Retry"
                                        onClick={() => handleRetryDocument(d)}
                                    >
                                        <RefreshCwIcon size={16} />
                                    </button>
                                )}
                                <button
                                    className="bg-nord11 h-7 rounded px-2"
                                    title="Delete"
                                    aria-label="Delete"
                                    onClick={() => handleDeleteDocument(d)}
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
                    title="Upload documents to start a new extraction run"
                >
                    <FilePlusIcon
                        className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                        size={48}
                    />
                    <div className="relative">Start new run</div>
                </Link>
                {hasTriples ? (
                    <Link
                        to={`/curation?ws=${wsId}`}
                        className="bg-nord8 relative flex h-24 w-32 items-center justify-center rounded px-2"
                        title={
                            dedupCounts.total > 0
                                ? `${dedupCounts.total - dedupCounts.pending} of ${dedupCounts.total} duplicate pair(s) reviewed`
                                : undefined
                        }
                    >
                        <MergeIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Deduplication</div>
                        {dedupCounts.total > 0 && (
                            <div className="absolute inset-x-0 bottom-1 text-center text-base font-semibold">
                                {dedupCounts.total - dedupCounts.pending} /{" "}
                                {dedupCounts.total}
                            </div>
                        )}
                    </Link>
                ) : (
                    <div
                        className="bg-nord8 relative flex h-24 w-32 cursor-not-allowed items-center justify-center rounded px-2 opacity-40"
                        title="No triples have been generated yet"
                        aria-disabled="true"
                    >
                        <MergeIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Deduplication</div>
                    </div>
                )}
                {hasTriples ? (
                    <Link
                        to={`/query?ws=${wsId}`}
                        className="bg-nord8 relative flex h-24 w-32 items-center justify-center rounded px-2"
                        title="Run SPARQL queries against the generated Knowledge Graph"
                    >
                        <SearchIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Queries</div>
                    </Link>
                ) : (
                    <div
                        className="bg-nord8 relative flex h-24 w-32 cursor-not-allowed items-center justify-center rounded px-2 opacity-40"
                        title="No triples have been generated yet"
                        aria-disabled="true"
                    >
                        <SearchIcon
                            className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                            size={48}
                        />
                        <div className="relative">Queries</div>
                    </div>
                )}
                <button
                    disabled={!hasTriples}
                    title={
                        hasTriples
                            ? "Export curated triples as JSON-LD or Turtle"
                            : "No triples have been generated yet"
                    }
                    className="bg-nord8 relative h-24 w-32 rounded px-2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                    <ShareIcon
                        className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                        size={48}
                    />
                    <div className="relative">Export</div>
                </button>
            </div>
            {ws?.role === "owner" && (
                <>
                    <h3 className="text-lg font-semibold">Invite Members</h3>
                    <InviteMembersSection
                        invites={pendingInvites}
                        onChange={handleInviteChange}
                        existingMembers={members}
                        onRemoveMember={handleRemoveMember}
                    />
                    {inviteError && (
                        <p className="text-nord11 text-sm">{inviteError}</p>
                    )}
                </>
            )}
        </Panel>
    );
}
