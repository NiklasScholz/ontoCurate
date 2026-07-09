import type { ReactNode } from "react";

export default function Panel({
    children,
    className,
}: {
    children: ReactNode;
    className?: string;
}) {
    return (
        <div className={`bg-nord6 rounded p-4 shadow-xl ${className}`}>
            {children}
        </div>
    );
}
