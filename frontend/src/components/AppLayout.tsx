import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import Avatar from "./Avatar";
import Root from "./Root";

export default function AppLayout() {
    const { currentUser, loading } = useAuth();
    if (loading) return null;
    if (!currentUser) return <Navigate to="/" replace />;

    return (
        <div className="flex h-screen flex-col">
            <header className="bg-nord0 flex items-center justify-end px-4 py-2">
                <Avatar />
            </header>
            <main className="flex min-h-0 flex-1 flex-col">
                <Root>
                    <Outlet />
                </Root>
            </main>
        </div>
    );
}
