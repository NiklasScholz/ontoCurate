import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { ArrowLeftIcon } from "lucide-react";
import { client, getErrorMessage } from "../client";
import Spinner from "../components/Spinner";
import Panel from "../components/Panel";
import NotFound from "./NotFound";
import type { Graph, QueryResult } from "../types";

// paco/prov prefixes are only available in the curation graph for our onboarded use cases
// If data is supposed to be extracted using prov ontology, this needs to be adapted 
const CURATION_ONLY_PREFIXES = new Set(["paco", "prov"]);

export default function QueryPage() {
    const [searchParams] = useSearchParams();
    const wsId = searchParams.get("ws");

    const [ws, setWs] = useState<
        { id: string; name: string; role: string } | undefined
    >(undefined);
    const [prefixes, setPrefixes] = useState<
        Record<string, string> | undefined
    >(undefined);
    const [graph, setGraph] = useState<Graph>("data");
    
    // Kept seperate so switching between graphs for owner does not overwrite prior queries they want to continue using
    const [dataQuery, setDataQuery] = useState("");
    const [dataQueryEdited, setDataQueryEdited] = useState(false);
    const [curationQuery, setCurationQuery] = useState("");
    const [curationQueryEdited, setCurationQueryEdited] = useState(false);

    const query = graph === "data" ? dataQuery : curationQuery;
    const setQuery = graph === "data" ? setDataQuery : setCurationQuery;
    
    const queryEdited =
        graph === "data" ? dataQueryEdited : curationQueryEdited;
    const setQueryEdited =
        graph === "data" ? setDataQueryEdited : setCurationQueryEdited;
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<QueryResult | undefined>(undefined);

    useEffect(() => {
        if (wsId === null) return;
        client
            .GET("/workspaces/{workspace_id}", {
                params: { path: { workspace_id: wsId } },
            })
            .then((res) => setWs(res.data));
    }, [wsId]);

    useEffect(() => {
        if (wsId === null) return;
        client
            .GET("/workspaces/{workspace_id}/prefixes", {
                params: { path: { workspace_id: wsId } },
            })
            .then((res) => setPrefixes(res.data));
    }, [wsId]);

    const defaultQuery = prefixes
        ? `${Object.entries(prefixes)
              .filter(
                  ([prefix]) =>
                      graph === "curation" ||
                      !CURATION_ONLY_PREFIXES.has(prefix),
              )
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([prefix, uri]) => `PREFIX ${prefix}: <${uri}>`)
              .join("\n")}\n\nSELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 50`
        : "";
    const displayedQuery = queryEdited ? query : defaultQuery;

    const runQuery = async (queryText: string = displayedQuery) => {
        if (!wsId) return;
        setRunning(true);
        setError(null);
        const { data, error: reqError } = await client.POST(
            "/workspaces/{workspace_id}/query",
            {
                params: { path: { workspace_id: wsId } },
                body: { query: queryText, graph },
            },
        );
        setRunning(false);
        if (reqError) {
            setResult(undefined);
            setError(getErrorMessage(reqError, "Query failed"));
            return;
        }
        setResult(data);
    };

    if (wsId === null) {
        return <NotFound />;
    }

    return (
        <Panel className="flex w-240 flex-col gap-3">
            <div className="relative mb-2">
                <Link
                    to={`/workspace?ws=${wsId}`}
                    className="bg-nord4 absolute top-0 left-0 flex h-full w-12 items-center justify-center rounded"
                >
                    <ArrowLeftIcon size={16} />
                </Link>
                <h1 className="text-center text-xl">
                    {ws ? <>Query - {ws.name}</> : <Spinner />}
                </h1>
            </div>

            <div className="flex justify-center gap-4">
                {ws?.role === "owner" ? (
                    <>
                        <label className="flex items-center gap-1">
                            <input
                                type="radio"
                                name="graph"
                                checked={graph === "data"}
                                onChange={() => setGraph("data")}
                            />
                            Data Graph
                        </label>
                        <label className="flex items-center gap-1">
                            <input
                                type="radio"
                                name="graph"
                                checked={graph === "curation"}
                                onChange={() => setGraph("curation")}
                            />
                            Curation Graph (provenance)
                        </label>
                    </>
                ) : (
                    <span>Data Graph</span>
                )}
            </div>

            <textarea
                className="border-nord4 h-64 rounded border p-2 font-mono text-sm"
                value={displayedQuery}
                onChange={(e) => {
                    setQuery(e.target.value);
                    setQueryEdited(true);
                }}
                spellCheck={false}
            />

            <div className="flex justify-center">
                <button
                    className="bg-nord8 h-8 w-32 rounded disabled:opacity-50"
                    onClick={() => runQuery()}
                    disabled={running || !displayedQuery.trim()}
                >
                    {running ? <Spinner /> : "Run query"}
                </button>
            </div>

            {error && <p className="text-nord11 text-sm">{error}</p>}

            {result &&
                (result.boolean !== undefined && result.boolean !== null ? (
                    <div className="text-center text-lg">
                        {String(result.boolean)}
                    </div>
                ) : result.rows.length === 0 ? (
                    <div className="text-center italic">No results.</div>
                ) : (
                    <div className="flex max-h-[32rem] flex-col overflow-scroll text-sm">
                        <div
                            className="bg-nord6 sticky top-0 grid gap-5 font-bold"
                            style={{
                                gridTemplateColumns: `repeat(${result.variables.length}, 1fr)`,
                            }}
                        >
                            {result.variables.map((v) => (
                                <div
                                    key={v}
                                    className="overflow-hidden text-nowrap text-ellipsis"
                                >
                                    {v}
                                </div>
                            ))}
                        </div>
                        {result.rows.map((row, i) => (
                            <div
                                key={i}
                                className="even:bg-nord4 grid gap-5"
                                style={{
                                    gridTemplateColumns: `repeat(${result.variables.length}, 1fr)`,
                                }}
                            >
                                {result.variables.map((v) => (
                                    <div
                                        key={v}
                                        className={`overflow-hidden text-nowrap text-ellipsis ${
                                            row[v]?.type === "uri"
                                                ? "font-mono"
                                                : ""
                                        }`}
                                    >
                                        {row[v]?.value ?? ""}
                                    </div>
                                ))}
                            </div>
                        ))}
                    </div>
                ))}
        </Panel>
    );
}
