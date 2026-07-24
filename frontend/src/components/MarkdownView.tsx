import { useEffect, useMemo, useRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";
import type { Code, InlineCode, Root, Text } from "mdast";
import type {} from "mdast-util-to-hast";
import type { VFile } from "vfile";

export type HighlightRole = "subject" | "object";

export type HighlightSpan = { start: number; end: number; role: HighlightRole };

const HIGHLIGHT_COLOR: Record<HighlightRole, string> = {
    subject: "bg-nord15",
    object: "bg-nord13",
};

const HIGHLIGHT_CLASS: Record<HighlightRole, string> = {
    subject: "md-highlight-subject",
    object: "md-highlight-object",
};


// The only mdast node types that hold raw text characters.
type LeafNode = Text | InlineCode | Code;
const LEAF_TYPES = ["text", "inlineCode", "code"] as const;

/**
 * Wraps spans of text into mark nodes in the markdown AST, before it is converted to HTML by ReactMarkdown.
 *
 * Example used in the comments below: a text node with
 * node.value = "knows" (nodeStart=0, nodeEnd=5) and one span
 * {start: 1, end: 4} highlighting "now". The final result is three nodes: "k" | <mark>now</mark> | "s".
 * In a real document the nodeStart and nodeEnd are offsets into the original text (except for missing delimiters), and the span start and end are offsets into the same text.
 */
function remarkHighlightSpan(spans: HighlightSpan[]) {
    // Filter invalid spans and sort by start
    const sorted = [...spans]
        .filter((s) => s.start < s.end)
        .sort((a, b) => a.start - b.start);

    return (tree: Root, file: VFile) => {
        if (sorted.length === 0) return;
        const source = String(file.value);

        visit(
            tree,
            LEAF_TYPES,
            (node, index, parent) => {
                if (index === undefined || !parent) return;

                let nodeStart = node.position?.start.offset;
                let nodeEnd = node.position?.end.offset;
                if (nodeStart == null || nodeEnd == null) return;

                // realign with delimiters not included in node value but original text
                if (nodeEnd - nodeStart !== node.value.length) {
                    const contentStart = source.indexOf(node.value, nodeStart);
                    if (contentStart === -1 || contentStart + node.value.length > nodeEnd) {
                        return;
                    }
                    nodeStart = contentStart;
                    nodeEnd = contentStart + node.value.length;
                }

                // Keep only spans that touch this node's range at all 
                // "knows" example: overlapping = [{start: 1, end: 4}].
                const overlapping = sorted.filter(
                    (s) => s.start < nodeEnd && s.end > nodeStart,
                );
                if (overlapping.length === 0) return;

                // Get cut points that split the node into marked/non-marked pieces
                // e.g., "knows" split into "k" | "now" | "s"
                const cuts = new Set<number>([nodeStart, nodeEnd]);
                for (const s of overlapping) {
                    cuts.add(Math.max(s.start, nodeStart));
                    cuts.add(Math.min(s.end, nodeEnd));
                }
                const points = [...cuts].sort((a, b) => a - b);

                const replacement: LeafNode[] = [];
                for (let i = 0; i < points.length - 1; i++) {
                    const segStart = points[i];
                    const segEnd = points[i + 1];
                    if (segStart >= segEnd) continue;

                    // Slice out actual text
                    const value = node.value.slice(
                        segStart - nodeStart,
                        segEnd - nodeStart,
                    );

                    // Object role gets higher priority than subject role on overlap otherwise first match wins.
                    const covering =
                        overlapping.find(
                            (s) =>
                                s.role === "object" &&
                                s.start <= segStart &&
                                s.end >= segEnd,
                        ) ??
                        overlapping.find(
                            (s) => s.start <= segStart && s.end >= segEnd,
                        );

                    if (!covering) {
                        replacement.push({ type: node.type, value });
                        continue;
                    }
                    // Add new mark node with a role class - the mark
                    // component below reads it back to pick a color.
                    replacement.push({
                        type: node.type,
                        value,
                        data: {
                            hName: "mark",
                            hProperties: {
                                className: ["md-highlight", HIGHLIGHT_CLASS[covering.role]],
                            },
                        },
                    });
                }

                // Swap "knows" node for its three pieces
                // e.g. ("k", <mark>now</mark>, "s") in the parent's children.
                parent.children.splice(index, 1, ...replacement);
                // Skip past the nodes we just inserted
                return index + replacement.length;
            },
        );
    };
}

// Omits node from props to avoid ReactMarkdown warning about unknown prop on DOM element
function omitNode<P extends { node?: unknown }>(props: P): Omit<P, "node"> {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { node, ...rest } = props;
    return rest;
}

// Custom ReactMarkdown components to apply Tailwind classes to headings, lists, tables, and links
const components: Components = {
    h1: (props) => (
        <h1 className="mt-4 mb-2 text-2xl font-bold text-nord0 first:mt-0" {...omitNode(props)} />
    ),
    h2: (props) => (
        <h2 className="mt-4 mb-2 text-xl font-bold text-nord0 first:mt-0" {...omitNode(props)} />
    ),
    h3: (props) => (
        <h3 className="mt-3 mb-1 text-lg font-bold text-nord0 first:mt-0" {...omitNode(props)} />
    ),
    ul: (props) => <ul className="mb-2 list-disc pl-6" {...omitNode(props)} />,
    ol: (props) => <ol className="mb-2 list-decimal pl-6" {...omitNode(props)} />,
    a: (props) => (
        <a
            className="text-nord10 underline"
            target="_blank"
            rel="noreferrer"
            {...omitNode(props)}
        />
    ),
    table: (props) => (
        <table className="mb-2 border-collapse border border-nord4" {...omitNode(props)} />
    ),
    th: (props) => (
        <th className="border border-nord4 px-2 py-1 text-left font-bold" {...omitNode(props)} />
    ),
    td: (props) => <td className="border border-nord4 px-2 py-1" {...omitNode(props)} />,
    mark: ({ className, ...props }) => {
        const role: HighlightRole = className?.includes(HIGHLIGHT_CLASS.subject)
            ? "subject"
            : "object";
        const color = HIGHLIGHT_COLOR[role];
        return (
            <mark
                className={["rounded mix-blend-multiply", color, className]
                    .filter(Boolean)
                    .join(" ")}
                {...omitNode(props)}
            />
        );
    },
};

export default function MarkdownView({
    text,
    spans,
}: {
    text: string;
    spans: HighlightSpan[];
}) {
    const containerRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (spans.length === 0) return;
        const container = containerRef.current;
        // Always jump to object if available
        const target =
            container?.querySelector(".md-highlight-object") ??
            container?.querySelector(".md-highlight");
        target?.scrollIntoView({ block: "center" });
    }, [text, spans]);

    const rendered = useMemo(
        () => (
            <ReactMarkdown
                remarkPlugins={[remarkGfm, () => remarkHighlightSpan(spans)]}
                components={components}
            >
                {text}
            </ReactMarkdown>
        ),
        [text, spans],
    );

    return (
        <div ref={containerRef} className="h-full overflow-y-scroll">
            {rendered}
        </div>
    );
}
