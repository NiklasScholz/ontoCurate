import { useEffect, useRef } from "react";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import {
    EditorState,
    StateEffect,
    StateField,
    Transaction,
} from "@codemirror/state";
import {
    defaultHighlightStyle,
    syntaxHighlighting,
} from "@codemirror/language";

type Highlight = { start: number; end: number } | undefined;

const setHighlight = StateEffect.define<Highlight>();

const highlightField = StateField.define<DecorationSet>({
    create: function (): DecorationSet {
        return Decoration.none;
    },
    update: function (
        value: DecorationSet,
        transaction: Transaction,
    ): DecorationSet {
        for (const e of transaction.effects) {
            if (e.is(setHighlight)) {
                value = Decoration.none.update({
                    add:
                        e.value === undefined
                            ? []
                            : [highlightMark.range(e.value.start, e.value.end)],
                });
            }
        }
        return value;
    },
    provide: (f) => EditorView.decorations.from(f),
});

const highlightTheme = EditorView.baseTheme({
    ".cm-highlight": { textDecoration: "underline 3px red" },
});

const highlightMark = Decoration.mark({ class: "cm-highlight" });

export default function MarkdownView({
    text,
    span,
}: {
    text: string;
    span:
        | {
              start: number;
              end: number;
          }
        | undefined;
}) {
    const domRef = useRef<HTMLDivElement | null>(null);
    const viewRef = useRef<EditorView | undefined>(undefined);

    useEffect(() => {
        viewRef.current = new EditorView({
            doc: text,
            parent: domRef.current!,
            extensions: [
                highlightField,
                highlightTheme,
                EditorState.readOnly.of(true),
                EditorView.lineWrapping,
                syntaxHighlighting(defaultHighlightStyle),
                markdown(),
            ],
        });

        return () => {
            viewRef.current?.destroy();
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        if (!viewRef.current) return;
        const view = viewRef.current;
        const effects = [];
        effects.push(setHighlight.of(span));
        if (span) {
            effects.push(EditorView.scrollIntoView(span.start));
        }
        view.dispatch(view.state.update({ effects }));
    }, [span]);

    return (
        <div className="h-full overflow-scroll">
            <div ref={domRef}></div>
        </div>
    );
}
