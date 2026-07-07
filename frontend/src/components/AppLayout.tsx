import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import Avatar from "./Avatar";

export default function AppLayout() {
    const { currentUser, loading } = useAuth();
    if (loading) return null;
    if (!currentUser) return <Navigate to="/" replace />;

    return (
        <div className="flex min-h-screen flex-col">
            <header className="bg-nord6 flex items-center justify-end px-4 py-2">
                <Avatar />
            </header>
            <main className="flex flex-1 flex-col">
                <Outlet />
            </main>
        </div>
    );
}
