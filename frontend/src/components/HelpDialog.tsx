import { useEffect, useState } from "react";
import { ExternalLinkIcon, XIcon } from "lucide-react";
import { useLocation, useSearchParams } from "react-router-dom";
import { client } from "../client";

const REPO_URL =
    "https://gitlab.git.nrw/rwth-dbis/teaching/kglab/ss2026/onto-curate";

const STEPS = [
    "Create or open a shared workspace with a configured ontology",
    "Start a new extraction run with your documents",
    "Review the triples in the curation interface and accept, edit, or reject them",
    "Export the curated triples to json-ld or ttl format for use in other tools",
];

const STEPS_PATHS = ["/", "/create-workspace", "/workspace", "/workspaces", "/upload"];

type ConfidenceBand = {
    range: string;
    label: string;
    colorClass: string;
    description: string;
};

const CONFIDENCE_BANDS: ConfidenceBand[] = [
    {
        range: "0.90 - 1.00",
        label: "High",
        colorClass: "bg-nord14",
        description: "The value was found exactly (or case-insensitive) in the source text.",
    },
    {
        range: "0.75 - 0.89",
        label: "Medium",
        colorClass: "bg-nord13",
        description:
            "Matched after normalizing whitespace/markdown, as an abbreviation, or as a date written differently than extracted.",
    },
    {
        range: "0.50 - 0.74",
        label: "Low",
        colorClass: "bg-nord12",
        description: "Only a fuzzy, partial sentence-level similarity to the source text was found. The LLM has either hallucinated or used its knowledge to infer the value without its explicit presence.",
    },
    {
        range: "General Penalties",
        label: "Penalized",
        colorClass: "bg-nord11",
        description:
            "The match did not appear in the expected section/context for that field, or is an outlier relative to the position of related entities (e.g. an author far from the others).",
    },
];

const PAGE_HELP: Record<
    string,
    {
        title: string;
        body: string;
        confidenceTable?: boolean;
        showSchemaLink?: boolean;
    }
> = {
    "/workspaces": {
        title: "Workspaces",
        body: "Pick a workspace to open, or create a new one to start a fresh project with your team.",
    },
    "/create-workspace": {
        title: "Create workspace",
        body: "Name your workspace and invite collaborators as owners or editors. Choose the ontology suitable for your usecase.",
    },
    "/workspace": {
        title: "Workspace",
        body: "Upload documents and start extraction runs guided by the workspace's ontology. Once a run finishes, open the document or deduplicaion view to review generated triples. You can also export the triples to json-ld or ttl format for use in other tools.",
        showSchemaLink: true,
    },
    "/upload": {
        title: "Upload",
        body: "Upload the documents you want to extract knowledge triples from. This will start the LLM extraction process guided by the ontology specified for this workspace. Note that depending on the ontology and currently submitted runs, the extraction process may take some time to complete. For deeply nested schemas and many documents, this can possibly take multiple hours due to the recursive prompting of LLMs.",
        showSchemaLink: true,
    },
    "/curation": {
        title: "Curation",
        body: "Browse extracted triples on the left. Click one to inspect the source text, confidence and graph neighborhood, then accept, edit, or reject it. Bulk Accept is available for high-confidence triples.\n\nPlease note that these confidence scores are based on syntactic and semantic heuristics and may not always be accurately reflective of the true quality of LLM extracted triples. We recommend reviewing all triples broadly before accepting via bulk. \n\nThe table reflects the scores for extraction confidence. Please note that alignment confidence scores follow different heuristics (i.e., they will always be above a certain threshold based on semantic, syntactic and structural similarity as configured for the ontology).",
        confidenceTable: true,
        showSchemaLink: true,
    },
};

export default function HelpDialog({ onClose }: { onClose: () => void }) {
    const location = useLocation();
    const [searchParams] = useSearchParams();
    const pageHelp = PAGE_HELP[location.pathname];
    const showSteps = STEPS_PATHS.includes(location.pathname);

    const workspaceId = searchParams.get("ws");
    const [workspaceSchema, setWorkspaceSchema] = useState<
        { workspaceId: string; repoPath: string } | undefined
    >(undefined);

    useEffect(() => {
        if (!workspaceId) return;
        client
            .GET("/workspaces/{workspace_id}", {
                params: { path: { workspace_id: workspaceId } },
            })
            .then(({ data }) => {
                if (data?.schema_repo_path)
                    setWorkspaceSchema({
                        workspaceId,
                        repoPath: data.schema_repo_path,
                    });
            });
    }, [workspaceId]);

    const schemaRepoPath =
        workspaceSchema?.workspaceId === workspaceId
            ? workspaceSchema.repoPath
            : undefined;

    return (
        <div className="bg-nord6 flex max-h-[80vh] w-full max-w-xl flex-col gap-4 overflow-y-auto rounded p-4 shadow-xl">
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold">
                    {showSteps ? "How it works" : "Help"}
                </h2>
                <button onClick={onClose} className="hover:text-nord11">
                    <XIcon size={18} />
                </button>
            </div>

            {showSteps && (
                <ol className="flex flex-col gap-2">
                    {STEPS.map((step, i) => (
                        <li key={i} className="flex items-center gap-3">
                            <span className="bg-nord8 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white">
                                {i + 1}
                            </span>
                            <span className="text-base">{step}</span>
                        </li>
                    ))}
                </ol>
            )}

            {pageHelp && (
                <div className="border-nord4 flex flex-col gap-1 border-t pt-3">
                    <span className="text-base font-medium">Information about {pageHelp.title}</span>
                    <p className="text-base whitespace-pre-line opacity-80">{pageHelp.body}</p>

                    {pageHelp.showSchemaLink && schemaRepoPath && (
                        <a
                            href={`${REPO_URL}/-/blob/main/${schemaRepoPath}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-nord10 flex items-center gap-1 text-base"
                        >
                            View this workspace's schema in the repository
                            <ExternalLinkIcon size={14} />
                        </a>
                    )}

                    {pageHelp.confidenceTable && (
                        <table className="mt-2 w-full border-collapse text-left text-base">
                            <thead>
                                <tr className="border-nord4 border-b">
                                    <th className="py-1 pr-2 font-medium">Score</th>
                                    <th className="py-1 pr-2 font-medium">Level</th>
                                    <th className="py-1 font-medium">What it means</th>
                                </tr>
                            </thead>
                            <tbody>
                                {CONFIDENCE_BANDS.map((band) => (
                                    <tr key={band.label} className="border-nord4 border-b align-top last:border-b-0">
                                        <td className="py-1.5 pr-2 whitespace-nowrap opacity-80">{band.range}</td>
                                        <td className="py-1.5 pr-2 whitespace-nowrap">
                                            <span className="inline-flex items-center gap-1.5">
                                                <span className={`h-2 w-2 shrink-0 rounded-full ${band.colorClass}`} />
                                                {band.label}
                                            </span>
                                        </td>
                                        <td className="py-1.5 opacity-80">{band.description}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}
        </div>
    );
}
