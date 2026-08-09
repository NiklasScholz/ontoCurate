import { Link } from "react-router-dom";
import { TrashIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { client } from "../client";
import Spinner from "../components/Spinner";
import Panel from "../components/Panel";

export default function WorkspacesPage() {
    const [workspaces, setWorkspaces] = useState<
        { id: string; name: string; role: string }[] | undefined
    >(undefined);

    function reload() {
        client.GET("/workspaces/").then(({ data }) => setWorkspaces(data));
    }

    useEffect(reload, []);

    return (
        <Panel className="w-160 flex-col gap-2">
            {workspaces === undefined ? (
                <Spinner />
            ) : workspaces.length === 0 ? (
                <div className="italic">No workspace created yet</div>
            ) : (
                <div className="grid max-h-[60vh] grid-cols-4 gap-6 overflow-y-auto">
                    {workspaces.map((ws) => (
                        <Link
                            to={`/workspace?ws=${ws.id}`}
                            key={ws.name}
                            className="bg-nord4 relative flex h-32 items-center justify-center rounded-lg"
                        >
                            <div className="line-clamp-3 max-w-full px-4 text-center break-words">
                                {ws.name}
                            </div>
                            <span className="bg-nord8 absolute bottom-2 left-2 rounded px-2 py-0.5 text-xs text-white">
                                {ws.role}
                            </span>
                            <button
                                className="hover:text-nord11 absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded"
                                onClick={async (e) => {
                                    e.preventDefault();
                                    await client.DELETE(
                                        "/workspaces/{workspace_id}",
                                        {
                                            params: {
                                                path: {
                                                    workspace_id: ws.id,
                                                },
                                            },
                                        },
                                    );
                                    reload();
                                }}
                            >
                                <TrashIcon size={16} />
                            </button>
                        </Link>
                    ))}
                </div>
            )}

            <div className="mt-4 flex justify-center">
                <Link
                    to="/create-workspace"
                    className="bg-nord8 flex h-7 items-center rounded px-2 text-sm"
                >
                    Create Workspace
                </Link>
            </div>
        </Panel>
    );
}
