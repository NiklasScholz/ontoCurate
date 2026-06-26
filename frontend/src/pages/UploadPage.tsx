import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Root from "../components/Root";
import Panel from "../components/Panel";
import { ArrowLeftIcon, FileIcon, TrashIcon } from "lucide-react";
import { useState, type DragEvent } from "react";
import { client } from "../client";
import NotFound from "./NotFound";

export default function UploadPage() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const wsId = searchParams.get("ws");

    const [files, setFiles] = useState<{ id: string; data: File }[]>([]);

    if (wsId === null) {
        return <NotFound />;
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

        for (const file of Array.from(e.dataTransfer.files)) {
            if (file.type !== "application/pdf") {
                alert("Only PDF files are accepted!");
                return;
            }
        }
        setFiles([
            ...files,
            ...Array.from(e.dataTransfer.files).map((data) => {
                return { id: crypto.randomUUID(), data };
            }),
        ]);
    }

    return (
        <Root>
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

                <div
                    className="border-nord3/50 flex min-h-24 items-center justify-center border-4 border-dashed"
                    onDragEnter={onDragEnter}
                    onDragLeave={onDragLeave}
                    onDragOver={onDragOver}
                    onDrop={onDrop}
                >
                    {files.length === 0 ? (
                        <div className="text-nord3 italic">Drop files here</div>
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
                                            files.filter(
                                                (f) => f.id !== file.id,
                                            ),
                                        );
                                    }}
                                >
                                    <TrashIcon size={16} />
                                </button>
                            </div>
                        ))
                    )}
                </div>

                <div className="mt-4 flex justify-center">
                    <button
                        disabled={files.length === 0}
                        className={`h-7 rounded px-2 ${files.length === 0 ? "bg-nord4 text-nord3/50" : "bg-nord8"}`}
                        onClick={async () => {
                            await client.POST("/extraction/", {
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
                            navigate(`/workspace?ws=${wsId}`);
                        }}
                    >
                        Submit
                    </button>
                </div>
            </Panel>
        </Root>
    );
}
