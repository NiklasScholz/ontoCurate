import { Link } from "react-router-dom";
import Root from "../components/Root";
import { ArrowLeftIcon, TrashIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { client } from "../client";

export default function WorkspacesPage() {
    const [workspaces, setWorkspaces] = useState<
        { id: string; name: string }[] | undefined
    >(undefined);

    function reload() {
        client.GET("/workspaces/").then(({ data }) => setWorkspaces(data));
    }

    useEffect(reload, []);

    return (
        <Root>
            <div className="bg-nord6 flex w-160 flex-col gap-2 rounded p-4 shadow-xl">
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
                    <div>Loading...</div>
                ) : workspaces.length === 0 ? (
                    <div className="italic">No workspace created yet</div>
                ) : (
                    <div className="grid grid-cols-4 gap-6">
                        {workspaces.map((ws) => (
                            <button
                                key={ws.name}
                                className="bg-nord4 relative flex h-32 items-center justify-center rounded-lg"
                                onClick={async () => {
                                    await client.DELETE(
                                        "/workspaces/{workspace_id}",
                                        {
                                            path: { workspace_id: ws.id },
                                        },
                                    );
                                    reload();
                                }}
                            >
                                <div>{ws.name}</div>
                                <div className="hover:text-nord11 absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded">
                                    <TrashIcon size={16} />
                                </div>
                            </button>
                        ))}
                    </div>
                )}

                <div className="mt-4 flex justify-center gap-2">
                    <input
                        type="text"
                        placeholder="Name"
                        name="password"
                        className="border-nord4 h-7 rounded border-2 px-2"
                    />
                    <button
                        className="bg-nord8 h-7 rounded px-2"
                        onClick={async () => {
                            await client.POST("/workspaces/");
                            reload();
                        }}
                    >
                        Create
                    </button>
                </div>
            </div>
        </Root>
    );
}
