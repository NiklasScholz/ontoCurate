import type { ReactNode } from "react";

export default function Popup({
    children,
    show,
}: {
    children: ReactNode;
    className?: string;
    show: boolean;
}) {
    return (
        <div
            className={`bg-nord0/50 fixed inset-0 flex items-center justify-center p-4 backdrop-blur ${!show ? "hidden" : ""}`}
        >
            <div>{children}</div>
        </div>
    );
}
