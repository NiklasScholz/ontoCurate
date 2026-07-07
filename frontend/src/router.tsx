import { createBrowserRouter } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import NotFound from "./pages/NotFound";
import WorkspacesPage from "./pages/WorkspacesPage";
import WorkspacePage from "./pages/WorkspacePage";
import CurationPage from "./pages/CurationPage";
import UploadPage from "./pages/UploadPage";
import AppLayout from "./components/AppLayout";

export const router = createBrowserRouter([
    {
        path: "/",
        element: <LoginPage />,
    },
    {
        element: <AppLayout />,
        children: [
            { path: "/workspaces", element: <WorkspacesPage /> },
            { path: "/workspace", element: <WorkspacePage /> },
            { path: "/upload", element: <UploadPage /> },
            { path: "/curation", element: <CurationPage /> }
        ]
    },
    { path: "*", element: <NotFound /> },
]);
