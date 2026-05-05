import axios from "axios";
import {
    ArrowLeftIcon,
    EditIcon,
    ShareIcon,
    TrashIcon,
    XIcon,
} from "lucide-react";
import { useEffect, useState, type ChangeEvent } from "react";

const API_URL = "http://127.0.0.1:8000";

function AuthView({
    onSubmit,
}: {
    onSubmit: (username: string, password: string) => void;
}) {
    const [formData, setFormData] = useState({
        username: "",
        password: "",
    });

    const onChange = (e: ChangeEvent<HTMLInputElement>) => {
        setFormData((prev) => ({
            ...prev,
            [e.target.name]: e.target.value,
        }));
    };

    return (
        <div className="bg-nord6 flex w-120 flex-col gap-2 rounded p-4 shadow-xl">
            <h1 className="mb-4 text-center text-xl">Login</h1>
            <input
                type="text"
                placeholder="Username"
                name="username"
                value={formData.username}
                onChange={onChange}
                className="border-nord4 h-7 rounded border-2 px-2"
            />
            <input
                type="text"
                placeholder="Password"
                name="password"
                value={formData.password}
                onChange={onChange}
                className="border-nord4 h-7 rounded border-2 px-2"
            />
            <div className="flex justify-center">
                <button
                    className="bg-nord8 h-7 rounded px-2"
                    onClick={() =>
                        onSubmit(formData.username, formData.password)
                    }
                >
                    Submit
                </button>
            </div>
        </div>
    );
}

function Spinner({}) {
    return <div>Loading...</div>;
}

function WorkspacesView({
    onSelect,
    onBack,
}: {
    onSelect: (workspace: string) => void;
    onBack: () => void;
}) {
    const [workspaces, setWorkspaces] = useState<
        { name: string }[] | undefined
    >(undefined);

    useEffect(() => {
        axios.get("/api/workspaces").then((res) => setWorkspaces(res.data));
    }, []);

    return (
        <div className="bg-nord6 flex w-160 flex-col gap-2 rounded p-4 shadow-xl">
            <div className="relative mb-4">
                <button
                    onClick={onBack}
                    className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                >
                    <ArrowLeftIcon size={16} />
                </button>
                <h1 className="text-center text-xl">Workspaces</h1>
            </div>

            {workspaces ? (
                <div className="grid grid-cols-4 gap-6">
                    {workspaces.map((ws) => (
                        <button
                            key={ws.name}
                            className="bg-nord4 relative flex h-32 items-center justify-center rounded-lg"
                            onClick={() => onSelect(ws.name)}
                        >
                            <div>{ws.name}</div>
                            <div className="hover:text-nord11 absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded">
                                <TrashIcon size={16} />
                            </div>
                        </button>
                    ))}
                </div>
            ) : (
                <Spinner />
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
                    onClick={() => {}}
                >
                    Create
                </button>
            </div>
        </div>
    );
}

function WorkspaceView({
    workspace,
    onBack,
}: {
    workspace: string;
    onBack: () => void;
}) {
    const [documents, setDocuments] = useState<
        | { name: string; extractedCount: number; pendingCount: number }[]
        | undefined
    >(undefined);

    useEffect(() => {
        axios
            .get("/api/documents", { params: { workspace } })
            .then((res) => setDocuments(res.data));
    }, []);

    return (
        <div className="bg-nord6 flex w-160 flex-col gap-2 rounded p-4 shadow-xl">
            <div className="relative mb-4">
                <button
                    onClick={onBack}
                    className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                >
                    <ArrowLeftIcon size={16} />
                </button>
                <h1 className="text-center text-xl">Workspace {workspace}</h1>
            </div>

            {documents ? (
                <div className="grid grid-cols-4 gap-2">
                    <div>Document</div>
                    <div>Extracted</div>
                    <div>Pending review</div>
                    <div></div>
                    {documents.map((d) => (
                        <div key={d.name} className="contents">
                            <div>{d.name}</div>
                            <div>{d.extractedCount}</div>
                            <div
                                className={
                                    d.pendingCount > 0
                                        ? "text-nord12"
                                        : "text-nord14"
                                }
                            >
                                {d.pendingCount}
                            </div>
                            <div className="flex gap-2">
                                <button
                                    className="bg-nord8 h-7 rounded px-2"
                                    onClick={() => {}}
                                >
                                    <EditIcon size={16} />
                                </button>
                                <button
                                    className="bg-nord4 h-7 rounded px-2"
                                    onClick={() => {}}
                                >
                                    <ShareIcon size={16} />
                                </button>
                                <button
                                    className="bg-nord11 h-7 rounded px-2"
                                    onClick={() => {}}
                                >
                                    <TrashIcon size={16} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <Spinner />
            )}

            <div className="mt-4 flex justify-center">
                <button className="bg-nord8 h-7 rounded px-2">
                    Upload new document
                </button>
            </div>
        </div>
    );
}

function LoggedInView({ onBack }: { onBack: () => void }) {
    const [workspace, setWorkspace] = useState<string | undefined>();

    return workspace ? (
        <WorkspaceView
            onBack={() => setWorkspace(undefined)}
            workspace={workspace}
        />
    ) : (
        <WorkspacesView onBack={onBack} onSelect={(ws) => setWorkspace(ws)} />
    );
}

export default function App({}) {
    const [user, setUser] = useState<string | undefined>("a");

    return (
        <div className="bg-nord7 text-nord0 box-border flex min-h-screen items-center justify-center px-6 py-4">
            {user ? (
                <LoggedInView onBack={() => setUser(undefined)} />
            ) : (
                <AuthView
                    onSubmit={async (username, password) => {
                        await axios.post("/api/login", null, {
                            params: { username, password },
                        });
                        setUser(username);
                    }}
                />
            )}
        </div>
    );
}
