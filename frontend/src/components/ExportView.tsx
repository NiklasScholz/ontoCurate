import { XIcon } from "lucide-react";
import { useState } from "react";
import { apiUrl } from "../client";
import Panel from "./Panel";

export default function ExportView({
    isOwner,
    workspace,
    onClose,
    document,
}: {
    isOwner: boolean;
    workspace: string;
    onClose: () => void;
    document: string | undefined;
}) {
    const [includeProvenance, setIncludeProvenance] = useState(false);
    const [format, setFormat] = useState<"turtle" | "json-ld">("turtle");

    function getUrl() {
        const kind = includeProvenance ? "provenance" : "data";
        return apiUrl(
            document === undefined
                ? `/workspaces/${workspace}/export/${kind}?format=${format}`
                : `/documents/${document}/export/${kind}?format=${format}`,
        );
    }

    return (
        <Panel className="w-120">
            <div className="mb-6 flex items-center justify-between">
                <h2 className="text-xl font-semibold">
                    Export
                    {document === undefined ? " workspace" : " document"}
                </h2>
                <button onClick={onClose} className="hover:text-nord11">
                    <XIcon size={18} />
                </button>
            </div>

            <div className="grid grid-cols-[auto_auto] gap-2">
                <label htmlFor="format">Format</label>
                <select
                    id="format"
                    className="bg-nord4 rounded px-2 py-1"
                    value={format}
                    onChange={(e) =>
                        setFormat(e.target.value as "turtle" | "json-ld")
                    }
                >
                    <option value="turtle">Turtle</option>
                    <option value="json-ld">JSON-LD</option>
                </select>

                <label
                    htmlFor="provenance"
                    className={!isOwner && "opacity-50"}
                    title={
                        isOwner
                            ? undefined
                            : "Only available to the workspace owner"
                    }
                >
                    Include provenance data
                </label>
                <input
                    id="provenance"
                    type="checkbox"
                    disabled={!isOwner}
                    className={!isOwner && "opacity-50"}
                    title={
                        isOwner
                            ? undefined
                            : "Only available to the workspace owner"
                    }
                    checked={includeProvenance}
                    onChange={(e) => setIncludeProvenance(e.target.checked)}
                />
            </div>

            <div className="mt-6 flex justify-center">
                <a
                    href={getUrl()}
                    className="bg-nord8 rounded px-2 py-1"
                    target="_blank"
                    rel="noreferrer"
                >
                    Export
                </a>
            </div>
        </Panel>
    );
}
