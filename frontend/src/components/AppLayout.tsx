import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import Avatar from "./Avatar";
import HelpButton from "./HelpButton";
import Root from "./Root";

export default function AppLayout() {
    const { currentUser, loading } = useAuth();
    if (loading) return null;
    if (!currentUser) return <Navigate to="/" replace />;

    return (
        <div className="flex h-screen flex-col">
            <header className="bg-nord0 relative flex items-center justify-end gap-3 px-4 py-2">
                <img
                    src="/logo.svg"
                    alt="Logo"
                    className="absolute top-1/2 left-4 h-14 -translate-y-1/2"
                />
                <div className="flex items-center gap-3">
                    <HelpButton />
                    <Avatar />
                </div>
            </header>
            <main className="flex min-h-0 flex-1 flex-col">
                <Root>
                    <Outlet />
                </Root>
            </main>
        </div>
    );
}
