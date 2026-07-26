import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiUrl, client } from "../client";
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
import {
    type ExistingMember,
    type PendingInvite,
} from "../components/InviteMembersPanel";
import InviteMembersSection from "../components/InviteMembersPanel";

export default function WorkspacePage() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    const [ws, setWs] = useState<
        { id: string; name: string; role: string } | undefined
    >(undefined);

    const [docs, setDocs] = useState<Document[]>(undefined);
    const [docStatus, setDocStatus] = useState<{ [id: string]: string }>({});
    const [members, setMembers] = useState<ExistingMember[]>([]);
    const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);
    const [inviteError, setInviteError] = useState<string | null>(null);

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
                    client
                        .GET("/documents/", {
                            params: { query: { workspace_id: wsId } },
                        })
                        .then((res) => setDocs(res.data));
                });
        }
        updateDocStatus();
        const interval = setInterval(updateDocStatus, 10000);
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
            window.alert(
                (error as { detail?: string }).detail ??
                    "Failed to delete document",
            );
            return;
        }
        setDocs((prev) => prev.filter((d) => d.id !== doc.id));
        setDocStatus((prev) => {
            const next = { ...prev };
            delete next[doc.id];
            return next;
        });
    };

    if (wsId === null) {
        return <NotFound />;
    }

    return (
        <Panel className="flex w-160 flex-col gap-2">
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

            {docs === undefined ? (
                <Spinner />
            ) : docs.length === 0 ? (
                <div className="text-center italic">
                    No documents have been uploaded yet.
                </div>
            ) : (
                <div className="grid max-h-[40vh] grid-cols-[1fr_auto_auto_auto_auto] items-center gap-x-6 gap-y-2 overflow-y-auto">
                    <div>Document</div>
                    <div>Uploaded</div>
                    {docs.some((d) => docStatus[d.id] === "done") ? (
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
                                    title="Share"
                                    aria-label="Share"
                                    onClick={() => {}}
                                >
                                    <ShareIcon size={16} />
                                </button>
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
                <Link
                    to={`/query?ws=${wsId}`}
                    className="bg-nord8 relative flex h-24 w-32 items-center justify-center rounded px-2"
                >
                    <SearchIcon
                        className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                        size={48}
                    />
                    <div className="relative">Queries</div>
                </Link>
                <button className="bg-nord8 relative h-24 w-32 rounded px-2">
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
