import { Link } from "react-router-dom";
import Root from "../components/Root";
import { ArrowLeftIcon, TrashIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { client } from "../client";
import Spinner from "../components/Spinner";
import Panel from "../components/Panel";

export default function WorkspacesPage() {
    const [workspaces, setWorkspaces] = useState<
        { id: string; name: string }[] | undefined
    >(undefined);

    const [name, setName] = useState<string | undefined>(undefined);

    function reload() {
        client.GET("/workspaces/").then(({ data }) => setWorkspaces(data));
    }

    useEffect(reload, []);

    return (
        <Root>
            <Panel className="w-160 flex-col gap-2">
                <div className="relative mb-4">
                    <Link
                        to="/"
                        className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                    >
                        <ArrowLeftIcon size={16} />
                    </Link>
                    <h1 className="text-center text-xl">Workspaces</h1>
                </div>

                {workspaces === undefined ? (
                    <Spinner />
                ) : workspaces.length === 0 ? (
                    <div className="italic">No workspace created yet</div>
                ) : (
                    <div className="grid grid-cols-4 gap-6">
                        {workspaces.map((ws) => (
                            <Link
                                to={`/workspace?ws=${ws.id}`}
                                key={ws.name}
                                className="bg-nord4 relative flex h-32 items-center justify-center rounded-lg"
                            >
                                <div>{ws.name}</div>
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

                <div className="mt-4 flex justify-center gap-2">
                    <input
                        type="text"
                        placeholder="Name"
                        onChange={(event) => setName(event.target.value)}
                        name="password"
                        className="border-nord4 h-7 rounded border-2 px-2"
                    />
                    <button
                        className="bg-nord8 h-7 rounded px-2"
                        onClick={async () => {
                            await client.POST("/workspaces/", {
                                body: { name },
                            });
                            reload();
                        }}
                    >
                        Create
                    </button>
                </div>
            </Panel>
        </Root>
    );
}
