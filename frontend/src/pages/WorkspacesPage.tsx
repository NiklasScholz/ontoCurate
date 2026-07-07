import { Link } from "react-router-dom";
import Root from "../components/Root";
import { SettingsIcon, TrashIcon, XIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { client } from "../client";
import Spinner from "../components/Spinner";
import Panel from "../components/Panel";
import Popup from "../components/Popup";

export default function WorkspacesPage() {
    const [workspaces, setWorkspaces] = useState<
        { id: string; name: string }[] | undefined
    >(undefined);

    const [name, setName] = useState<string>("");
    const [schemaPath, setSchemaPath] = useState<string>(
        "/app/config/schemas/scholarly_schema.yaml",
    );
    const [alignmentConfigPath, setAlignmentConfigPath] = useState<string>(
        "/app/config/schemas/alignment_config.yaml",
    );
    const [provenanceConfigPath, setProvenanceConfigPath] = useState<string>(
        "/app/config/schemas/provenance_config.yaml",
    );
    const [showConfigPopup, setShowConfigPopup] = useState<boolean>(false);

    function reload() {
        client.GET("/workspaces/").then(({ data }) => setWorkspaces(data));
    }

    useEffect(reload, []);

    return (
        <Root>
            <Panel className="w-160 flex-col gap-2">
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
                        className="border-nord4 h-7 rounded border-2 px-2"
                    />
                    <button onClick={() => setShowConfigPopup(true)}>
                        <SettingsIcon />
                    </button>
                    <button
                        className="bg-nord8 h-7 rounded px-2"
                        onClick={async () => {
                            await client.POST("/workspaces/", {
                                body: {
                                    name,
                                    schema_path: schemaPath,
                                    alignment_config_path: alignmentConfigPath,
                                    provenance_config_path:
                                        provenanceConfigPath,
                                },
                            });
                            reload();
                        }}
                    >
                        Create
                    </button>
                </div>
            </Panel>

            <Popup show={showConfigPopup}>
                <Panel className="flex flex-col gap-2">
                    <div className="flex justify-end">
                        <button onClick={() => setShowConfigPopup(false)}>
                            <XIcon />
                        </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <label htmlFor="schemaPath">Schema path</label>
                        <input
                            type="text"
                            name="schemaPath"
                            value={schemaPath}
                            onChange={(event) =>
                                setSchemaPath(event.target.value)
                            }
                            className="border-nord4 h-7 rounded border-2 px-2"
                        />
                        <label htmlFor="alignmentConfigPath">
                            Alignment config path
                        </label>
                        <input
                            type="text"
                            name="alignmentConfigPath"
                            value={alignmentConfigPath}
                            onChange={(event) =>
                                setAlignmentConfigPath(event.target.value)
                            }
                            className="border-nord4 h-7 rounded border-2 px-2"
                        />
                        <label htmlFor="provenanceConfigPath">
                            Provenance config path
                        </label>
                        <input
                            type="text"
                            name="provenanceConfigPath"
                            value={provenanceConfigPath}
                            onChange={(event) =>
                                setProvenanceConfigPath(event.target.value)
                            }
                            className="border-nord4 h-7 rounded border-2 px-2"
                        />
                    </div>
                </Panel>
            </Popup>
        </Root>
    );
}
