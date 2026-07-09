import { useEffect, useState } from "react";
import { client } from "../client";
import InviteMembersSection, {
    type PendingInvite,
} from "../components/InviteMembersPanel";
import Panel from "../components/Panel";
import Spinner from "../components/Spinner";
import { ArrowLeftIcon } from "lucide-react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/useAuth";

export default function WorkspaceCreationPage() {
    const { currentUser } = useAuth();
    const navigate = useNavigate();
    const [name, setName] = useState("My Workspace");
    const [schemas, setSchemas] = useState<string[] | undefined>(undefined);
    const [schemasError, setSchemasError] = useState<string | null>(null);
    const [schemaName, setSchemaName] = useState("ScholarlySchema");
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState<string | null>(null);
    const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);

    useEffect(() => {
        client.GET("/schemas/").then(({ data, error }) => {
            const schemaNames = data as string[] | undefined;
            if (error || !schemaNames) {
                setSchemasError("Failed to load schemas");
                return;
            }
            setSchemas(schemaNames);
            if (!schemaNames.includes("ScholarlySchema"))
                setSchemaName(schemaNames[0] ?? "");
        });
    }, []);

    const handleSubmit = async () => {
        setSubmitting(true);
        setSubmitError(null);

        const { data: ws, error } = await client.POST("/workspaces/", {
            body: { name, schema_name: schemaName },
        });

        if (error || !ws) {
            setSubmitError(
                (error as { detail?: string })?.detail ??
                    "Failed to create workspace",
            );
            setSubmitting(false);
            return;
        }

        await Promise.all(
            pendingInvites.map((invite) =>
                client.POST("/workspaces/{workspace_id}/members", {
                    params: { path: { workspace_id: ws.id } },
                    body: { user_info: invite.user_info, role: invite.role },
                }),
            ),
        );

        navigate(`/workspace?ws=${ws.id}`);
    };

    const canSubmit =
        name.trim().length > 0 && schemas !== undefined && !submitting;

    return (
        <Panel className="flex w-160 flex-col gap-6">
            <div className="relative mb-4">
                <Link
                    to="/workspaces"
                    className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                >
                    <ArrowLeftIcon size={16} />
                </Link>
                <h1 className="text-center text-xl">
                    Create Workspace {name && <> - {name}</>}
                </h1>
            </div>

            <div className="flex flex-col gap-3">
                <h2 className="text-nord3 text-xs font-semibold tracking-widest uppercase">
                    Workspace Details
                </h2>

                <div className="flex flex-col gap-1">
                    <label className="text-sm">Name</label>
                    <input
                        type="text"
                        placeholder="My Workspace"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="border-nord4 h-8 rounded border-2 px-2 text-sm"
                    />
                </div>

                <div className="flex flex-col gap-1">
                    <label className="text-sm">Schema</label>
                    {schemasError ? (
                        <p className="text-nord11 text-sm">{schemasError}</p>
                    ) : schemas === undefined ? (
                        <Spinner />
                    ) : (
                        <select
                            value={schemaName}
                            onChange={(e) => setSchemaName(e.target.value)}
                            className="border-nord4 h-8 rounded border-2 px-2 text-sm"
                        >
                            {schemas.map((s) => (
                                <option key={s} value={s}>
                                    {s}
                                </option>
                            ))}
                        </select>
                    )}
                </div>
            </div>
            <div className="border-nord4 border-t" />
            <InviteMembersSection
                invites={pendingInvites}
                onChange={setPendingInvites}
                currentUserEmail={currentUser?.email}
            />
            {submitError && (
                <p className="text-nord11 text-sm">{submitError}</p>
            )}
            <div className="flex justify-end gap-2">
                <Link
                    to="/workspaces"
                    className="bg-nord4 flex h-8 items-center rounded px-4 text-sm"
                >
                    Cancel
                </Link>
                <button
                    onClick={handleSubmit}
                    disabled={!canSubmit}
                    className="bg-nord8 flex h-8 min-w-32 items-center justify-center rounded px-4 text-sm text-white disabled:opacity-40"
                >
                    {submitting ? <Spinner /> : "Create Workspace"}
                </button>
            </div>
        </Panel>
    );
}
