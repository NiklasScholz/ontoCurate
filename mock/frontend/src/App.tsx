import axios from "axios";
import {
    ArrowLeftIcon,
    ArrowRightIcon,
    CheckIcon,
    EditIcon,
    FilePlusIcon,
    ListIcon,
    MergeIcon,
    RotateCcwIcon,
    SearchIcon,
    ShareIcon,
    TrashIcon,
    UploadIcon,
    XIcon,
} from "lucide-react";
import { useEffect, useState, type ChangeEvent } from "react";
import MarkdownView from "./MarkdownView";

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

type Document = {
    text: string;
    annotations: Triple[];
};

type Triple = {
    subject: string;
    predicate: string;
    value: string;
    span_start: number;
    span_end: number;
    confidence: number;
};

type Neighborhood = {
    incoming: { edge: string; node: string }[];
    outgoing: { edge: string; node: string }[];
};

function LocalGraphView({
    center,
    incoming,
    outgoing,
}: {
    center: string;
} & Neighborhood) {
    const styles = getComputedStyle(document.documentElement);
    const nord0 = styles.getPropertyValue("--color-nord0");
    const nord4 = styles.getPropertyValue("--color-nord4");
    const nord8 = styles.getPropertyValue("--color-nord8");

    function calcY(i: number, n: number): number {
        return (i + 0.5) * (500 / n);
    }

    function text(s: string): string {
        const url = "http://example.org/scholarly-metadata-ontology";
        return s.startsWith(url) ? s.substring(url.length) : s;
    }

    return (
        <svg viewBox="0 0 800 500" className="h-full w-full">
            {incoming.map(({ edge, node }, i) => {
                return (
                    <>
                        <line
                            x1="100"
                            y1={calcY(i, incoming.length)}
                            x2="400"
                            y2="250"
                            stroke={nord4}
                            stroke-width="5"
                        />
                        <circle
                            r="30"
                            cx="100"
                            cy={calcY(i, incoming.length)}
                            fill={nord4}
                        />
                        <text
                            x="250"
                            y={(calcY(i, incoming.length) + 250) / 2}
                            text-anchor="middle"
                            dominant-baseline="middle"
                            fill={nord0}
                            font-size="18"
                        >
                            {text(edge)}
                        </text>
                        <text
                            x="100"
                            y={calcY(i, incoming.length)}
                            text-anchor="middle"
                            dominant-baseline="middle"
                            fill={nord0}
                            font-size="18"
                        >
                            {text(node)}
                        </text>
                    </>
                );
            })}
            {outgoing.map(({ edge, node }, i) => {
                return (
                    <>
                        <line
                            x1="400"
                            y1="250"
                            x2="700"
                            y2={calcY(i, outgoing.length)}
                            stroke={nord4}
                            stroke-width="5"
                        />
                        <circle
                            r="30"
                            cx="700"
                            cy={calcY(i, outgoing.length)}
                            fill={nord4}
                        />
                        <text
                            x="550"
                            y={(calcY(i, outgoing.length) + 250) / 2}
                            text-anchor="middle"
                            dominant-baseline="middle"
                            fill={nord0}
                            font-size="18"
                        >
                            {text(edge)}
                        </text>
                        <text
                            x="700"
                            y={calcY(i, outgoing.length)}
                            text-anchor="middle"
                            dominant-baseline="middle"
                            fill={nord0}
                            font-size="18"
                        >
                            {text(node)}
                        </text>
                    </>
                );
            })}
            <circle r="30" cx="400" cy="250" fill={nord8} />
            <text
                x="400"
                y="250"
                text-anchor="middle"
                dominant-baseline="middle"
                fill={nord0}
                font-size="18"
            >
                {text(center)}
            </text>
        </svg>
    );
}

function EntityView({ entity }: { entity: string }) {
    let [neighborhood, setNeighborhood] = useState<Neighborhood | undefined>(
        undefined,
    );

    useEffect(() => {
        axios
            .get("/api/kg/neighborhood", { params: { entity } })
            .then((res) => setNeighborhood(res.data));
    }, [entity]);

    return neighborhood ? (
        <div>
            <LocalGraphView
                center={entity}
                incoming={neighborhood.incoming}
                outgoing={neighborhood.outgoing}
            />
        </div>
    ) : (
        <Spinner />
    );
}

function TripleView({
    workspace,
    document,
    id,
    index,
    total,
    triple,
    onLeft,
    onBack,
    onRight,
}: {
    workspace: string;
    document: Document;
    id: string;
    index: number;
    total: number;
    triple: Triple;
    onLeft: () => void;
    onBack: () => void;
    onRight: () => void;
}) {
    return (
        <div className="bg-nord6 flex h-full w-full max-w-7xl flex-col gap-2 rounded p-4 shadow-xl">
            <div className="">
                <h1 className="text-center text-xl">
                    Triple {index + 1}/{total}
                </h1>
            </div>
            <div className="mb-4 flex justify-center gap-2">
                <button
                    disabled={index === 0}
                    onClick={onLeft}
                    className="bg-nord8 flex h-7 w-12 items-center justify-center rounded"
                >
                    <ArrowLeftIcon size={16} />
                </button>
                <button
                    onClick={onBack}
                    className="bg-nord4 flex h-7 w-12 items-center justify-center rounded"
                >
                    <ListIcon size={16} />
                </button>
                <button
                    disabled={index === total - 1}
                    onClick={onRight}
                    className="bg-nord8 flex h-7 w-12 items-center justify-center rounded"
                >
                    <ArrowRightIcon size={16} />
                </button>
            </div>

            <MarkdownView
                text={document.text}
                span={{ start: triple.span_start, end: triple.span_end }}
            />
            <div className="bg-nord4 rounded p-4">
                <div className="mb-4 flex justify-center gap-2">
                    <button className="bg-nord14 flex h-7 w-12 items-center justify-center rounded">
                        <CheckIcon size={16} />
                    </button>
                    <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                        <RotateCcwIcon size={16} />
                    </button>
                    <button className="bg-nord11 flex h-7 w-12 items-center justify-center rounded">
                        <XIcon size={16} />
                    </button>
                </div>
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-nord6 flex flex-col justify-between gap-2 rounded-t p-2">
                        <div className="font-mono text-sm wrap-anywhere">
                            {triple.subject}
                        </div>
                        <div className="flex justify-center gap-2">
                            <button className="bg-nord8 flex h-7 w-12 items-center justify-center rounded">
                                <EditIcon size={16} />
                            </button>
                            <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                                <RotateCcwIcon size={16} />
                            </button>
                        </div>
                    </div>
                    <div className="bg-nord6 flex flex-col justify-between gap-2 rounded p-2">
                        <div className="font-mono text-sm wrap-anywhere">
                            {triple.predicate}
                        </div>
                        <div className="flex justify-center gap-2">
                            <button className="bg-nord8 flex h-7 w-12 items-center justify-center rounded">
                                <EditIcon size={16} />
                            </button>
                            <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                                <RotateCcwIcon size={16} />
                            </button>
                        </div>
                    </div>
                    <div className="bg-nord6 flex flex-col justify-between gap-2 rounded-t p-2">
                        <div className="font-mono text-sm wrap-anywhere">
                            {triple.value}
                        </div>
                        <div className="flex justify-center gap-2">
                            <button className="bg-nord8 flex h-7 w-12 items-center justify-center rounded">
                                <EditIcon size={16} />
                            </button>
                            <button className="bg-nord4 flex h-7 w-12 items-center justify-center rounded">
                                <RotateCcwIcon size={16} />
                            </button>
                        </div>
                    </div>
                </div>
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-nord6 h-4"></div>
                    <div></div>
                    <div className="bg-nord6 h-4"></div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-nord6 rounded-tr rounded-b">
                        <EntityView entity={triple.subject} />
                    </div>
                    <div className="bg-nord6 rounded-tl rounded-b">
                        <EntityView entity={triple.value} />
                    </div>
                </div>
            </div>
        </div>
    );
}

function DocumentView({
    workspace,
    name,
    onBack,
}: {
    workspace: string;
    name: string;
    onBack: () => void;
}) {
    const [doc, setDoc] = useState<Document | undefined>(undefined);

    const [selected, setSelected] = useState<number | undefined>(undefined);

    useEffect(() => {
        axios
            .get("/api/documents/get", { params: { workspace, name } })
            .then((res) => setDoc(res.data));
    }, []);

    return selected !== undefined ? (
        <TripleView
            workspace={workspace}
            document={doc!}
            id={"a"}
            index={selected}
            total={doc!.annotations.length}
            triple={doc!.annotations[selected]}
            onLeft={() => setSelected(selected - 1)}
            onBack={() => setSelected(undefined)}
            onRight={() => setSelected(selected + 1)}
        />
    ) : (
        <div className="bg-nord6 flex h-full max-w-7xl flex-col gap-2 rounded p-4 shadow-xl">
            <div className="relative mb-4">
                <button
                    className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                    onClick={onBack}
                >
                    <ArrowLeftIcon size={16} />
                </button>
                <h1 className="text-center text-xl">Document {name}</h1>
            </div>

            {doc ? (
                <div className="grid h-full grid-cols-[1fr_auto_1fr] gap-4">
                    <div className="flex h-full flex-col overflow-scroll">
                        {doc.annotations
                            .filter((_triple, i) => i < 100)
                            .map((triple, i) => {
                                return (
                                    <button
                                        className="even:bg-nord4"
                                        onClick={() => setSelected(i)}
                                    >
                                        <div className="grid grid-cols-3">
                                            <div className="overflow-hidden text-nowrap text-ellipsis">
                                                {triple.subject}
                                            </div>
                                            <div className="overflow-hidden text-nowrap text-ellipsis">
                                                {triple.predicate}
                                            </div>
                                            <div className="overflow-hidden text-nowrap text-ellipsis">
                                                {triple.value}
                                            </div>
                                        </div>
                                    </button>
                                );
                            })}
                    </div>
                    <div className="bg-nord4 h-full w-0.5"></div>
                    <MarkdownView
                        text={doc.text}
                        span={
                            selected === undefined
                                ? undefined
                                : {
                                      start: doc.annotations[selected]
                                          .span_start,
                                      end: doc.annotations[selected].span_end,
                                  }
                        }
                    />
                </div>
            ) : (
                <Spinner />
            )}
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

    const [openDocument, setOpenDocument] = useState<string | undefined>(
        undefined,
    );

    useEffect(() => {
        axios
            .get("/api/documents", { params: { workspace } })
            .then((res) => setDocuments(res.data));
    }, []);

    return openDocument ? (
        <DocumentView
            workspace={workspace}
            name={openDocument}
            onBack={() => setOpenDocument(undefined)}
        />
    ) : (
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
                    <div>Extracted triples</div>
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
                                    onClick={() => {
                                        setOpenDocument(d.name);
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

            <div className="mt-4 flex justify-center gap-4">
                <button className="bg-nord8 relative h-24 w-32 rounded px-2">
                    <FilePlusIcon
                        className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                        size={48}
                    />
                    <div className="relative">Upload new document</div>
                </button>
                <button className="bg-nord8 relative h-24 w-32 rounded px-2">
                    <MergeIcon
                        className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                        size={48}
                    />
                    <div className="relative">Deduplication view</div>
                </button>
                <button className="bg-nord8 relative h-24 w-32 rounded px-2">
                    <SearchIcon
                        className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                        size={48}
                    />
                    <div className="relative">Query view</div>
                </button>
                <button className="bg-nord8 relative h-24 w-32 rounded px-2">
                    <ShareIcon
                        className="text-nord8-light absolute top-0 right-0 bottom-0 left-0 m-auto"
                        size={48}
                    />
                    <div className="relative">Export graph</div>
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
        <div className="bg-nord7 text-nord0 box-border flex h-screen items-center justify-center px-6 py-4">
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
