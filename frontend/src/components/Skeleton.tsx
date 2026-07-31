export function Skeleton({ className = "" }: { className?: string }) {
    return <div className={`bg-nord4 animate-pulse rounded ${className}`} />;
}

export function TableSkeleton({
    gridColsClassName,
    columns,
    rows = 8,
    className = "",
}: {
    gridColsClassName: string;
    columns: number;
    rows?: number;
    className?: string;
}) {
    const widths = ["w-2/3", "w-full", "w-5/6", "w-1/2", "w-3/4"];

    return (
        <div className={`grid gap-5 ${gridColsClassName} ${className}`}>
            {Array.from({ length: rows * columns }, (_, i) => (
                <Skeleton
                    key={i}
                    className={`h-4 ${widths[i % widths.length]}`}
                />
            ))}
        </div>
    );
}
