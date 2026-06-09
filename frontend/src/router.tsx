import { createBrowserRouter } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import NotFound from "./pages/NotFound";
import WorkspacesPage from "./pages/WorkspacesPage";
import WorkspacePage from "./pages/WorkspacePage";
import CurationOverviewPage from "./pages/CurationOverviewPage";
import CurationTriplePage from "./pages/CurationTriplePage";

export const router = createBrowserRouter([
    {
        path: "/",
        element: <LoginPage />,
    },
    { path: "/workspaces", element: <WorkspacesPage /> },
    { path: "/workspace:id", element: <WorkspacePage /> },
    { path: "/curation-overview", element: <CurationOverviewPage /> },
    { path: "/curation-triple", element: <CurationTriplePage /> },
    { path: "*", element: <NotFound /> },
]);
