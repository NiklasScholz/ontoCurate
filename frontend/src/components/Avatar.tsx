import { useEffect, useRef, useState } from "react";
import { LogOutIcon, UserXIcon } from "lucide-react";
import { useAuth } from "../context/useAuth";

export default function Avatar() {
    const { currentUser, logout, deleteAccount } = useAuth();
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        function handleClick(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        }
        document.addEventListener("mousedown", handleClick);
        return () => document.removeEventListener("mousedown", handleClick);
    }, []);

    if (!currentUser) return null;

    const initials = (currentUser.name ?? currentUser.email).slice(0, 2).toUpperCase();

    return (
        <div ref={ref} className="relative">
            <button
                onClick={() => setOpen((v) => !v)}
                className="flex h-8 w-8 items-center justify-center rounded-full overflow-hidden"
            >
                {currentUser.picture
                    ? <img
                        src={currentUser.picture}
                        alt={initials}
                        referrerPolicy="no-referrer"
                        className="h-full w-full object-cover"
                    />
                    : <span className="bg-nord8 flex h-full w-full items-center justify-center text-xs font-bold text-white">{initials}</span>
                }
            </button>
            {open && (
                <div className="bg-nord6 shadow-lg absolute right-0 top-10 z-10 flex w-64 flex-col rounded">
                    <div className="border-nord4 border-b px-3 py-2">
                        {currentUser.name && <div className="text-sm font-medium truncate">{currentUser.name}</div>}
                        <div className="text-xs text-gray-500 truncate">{currentUser.email}</div>
                    </div>
                    <button
                        onClick={() => { setOpen(false); logout(); }}
                        className="hover:bg-nord4 flex items-center gap-2 px-3 py-2 text-sm"
                    >
                        <LogOutIcon size={14} /> Logout
                    </button>
                    <button
                        onClick={() => { setOpen(false); if (confirm("Delete your account? This cannot be undone.")) deleteAccount(); }}
                        className="hover:bg-nord4 text-nord11 flex items-center gap-2 px-3 py-2 text-sm"
                    >
                        <UserXIcon size={14} /> Delete account
                    </button>
                </div>
            )}
        </div>
    );
}
