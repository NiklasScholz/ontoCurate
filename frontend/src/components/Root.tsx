import type { ReactNode } from "react";

export default function Root({
    children,
    className,
}: {
    children: ReactNode;
    className?: string;
}) {
    return (
        <div
            className={`bg-nord7 box-border flex h-screen items-center justify-center px-6 py-4 ${className}`}
        >
            {children}
        </div>
    );
}
