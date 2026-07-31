import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Panel from "../components/Panel";
import {
    ArrowLeftIcon,
    FileIcon,
    TrashIcon,
    TriangleAlertIcon,
} from "lucide-react";
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { client } from "../client";
import NotFound from "./NotFound";

export default function UploadPage() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const wsId = searchParams.get("ws");

    const [files, setFiles] = useState<{ id: string; data: File }[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    if (wsId === null) {
        return <NotFound />;
    }

    function addFiles(newFiles: FileList | File[]) {
        for (const file of Array.from(newFiles)) {
            if (!/\.(pdf|md)$/i.test(file.name)) {
                alert("Only PDF or Markdown files are accepted!");
                return;
            }
        }
        setFiles([
            ...files,
            ...Array.from(newFiles).map((data) => {
                return { id: crypto.randomUUID(), data };
            }),
        ]);
    }

    function onDragEnter(e: DragEvent<HTMLDivElement>) {
        e.preventDefault();
        e.stopPropagation();
    }

    function onDragLeave(e: DragEvent<HTMLDivElement>) {
        e.preventDefault();
        e.stopPropagation();
    }

    function onDragOver(e: DragEvent<HTMLDivElement>) {
        e.preventDefault();
        e.stopPropagation();
    }

    function onDrop(e: DragEvent<HTMLDivElement>) {
        e.preventDefault();
        e.stopPropagation();
        addFiles(e.dataTransfer.files);
    }

    function onFileInputChange(e: ChangeEvent<HTMLInputElement>) {
        if (e.target.files && e.target.files.length > 0) {
            addFiles(e.target.files);
        }
        e.target.value = "";
    }

    return (
        <Panel className="flex w-160 flex-col gap-2">
            <div className="relative mb-4">
                <Link
                    to={`/workspace?ws=${wsId}`}
                    className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                >
                    <ArrowLeftIcon size={16} />
                </Link>
                <h1 className="text-center text-xl">Upload documents</h1>
            </div>

            <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.md,text/markdown"
                multiple
                className="hidden"
                onChange={onFileInputChange}
            />

            <div
                className="border-nord3/50 flex max-h-[50vh] min-h-24 flex-wrap items-center justify-center gap-2 overflow-y-auto border-4 border-dashed p-2"
                onDragEnter={onDragEnter}
                onDragLeave={onDragLeave}
                onDragOver={onDragOver}
                onDrop={onDrop}
            >
                {files.length === 0 ? (
                    <div className="text-nord3 flex flex-col items-center gap-2 italic">
                        <span>Drop files here</span>
                        <span>or</span>
                        <button
                            type="button"
                            className="bg-nord4 text-nord0 rounded px-1.5 py-0.5 text-xs not-italic"
                            onClick={() => fileInputRef.current?.click()}
                        >
                            Browse files
                        </button>
                    </div>
                ) : (
                    files.map((file) => (
                        <div
                            key={file.id}
                            className="rounded-l4 relative flex h-32 w-32 items-center justify-center"
                        >
                            <div className="text-nord4 absolute inset-0 flex items-center justify-center">
                                <FileIcon size={92} />
                            </div>
                            <div className="absolute inset-6 flex items-center justify-center break-all">
                                {file.data.name}
                            </div>
                            <button
                                className="hover:text-nord11 absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded"
                                onClick={() => {
                                    setFiles(
                                        files.filter((f) => f.id !== file.id),
                                    );
                                }}
                            >
                                <TrashIcon size={16} />
                            </button>
                        </div>
                    ))
                )}
                {files.length > 0 && (
                    <button
                        type="button"
                        className="text-nord3 hover:bg-nord4 flex h-32 w-32 flex-col items-center justify-center gap-1 rounded text-sm"
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <span>+</span>
                        <span>Add files</span>
                    </button>
                )}
            </div>

            {error && (
                <p className="text-nord11 mt-2 flex items-center justify-center gap-2 text-sm">
                    <TriangleAlertIcon size={14} />
                    {error}
                </p>
            )}

            <div className="mt-4 flex justify-center">
                <button
                    disabled={files.length === 0 || submitting}
                    className={`h-7 rounded px-2 ${files.length === 0 || submitting ? "bg-nord4 text-nord3/50" : "bg-nord8"}`}
                    onClick={async () => {
                        setError(null);
                        setSubmitting(true);
                        const { error } = await client.POST("/extraction/", {
                            params: { query: { workspace_id: wsId } },
                            body: {
                                files: files.map(
                                    (file) => file.data,
                                ) as unknown as string[],
                            },
                            bodySerializer(body) {
                                const formData = new FormData();
                                (body.files as unknown as File[]).forEach(
                                    (file) => {
                                        formData.append("files", file);
                                    },
                                );
                                return formData;
                            },
                        });
                        setSubmitting(false);
                        if (error) {
                            const body = error as {
                                detail?: string | { msg: string }[];
                                error?: string;
                            };
                            const detail = Array.isArray(body.detail)
                                ? body.detail.map((d) => d.msg).join(", ")
                                : body.detail;
                            setError(
                                detail ??
                                    body.error ??
                                    "Failed to upload documents",
                            );
                            return;
                        }
                        navigate(`/workspace?ws=${wsId}`);
                    }}
                >
                    {submitting ? "Uploading…" : "Submit"}
                </button>
            </div>
        </Panel>
    );
}
