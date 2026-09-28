import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/app.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { Layout } from "./components/Layout";
import { LoadingBlock, ToastProvider } from "./components/ui";
import { Compliance } from "./pages/Compliance";
import { FindingDetail } from "./pages/FindingDetail";
import { Findings } from "./pages/Findings";
import { Integrity } from "./pages/Integrity";
import { Intelligence } from "./pages/Intelligence";
import { Overview } from "./pages/Overview";
import { Rulebook } from "./pages/Rulebook";

// Cytoscape is the heaviest dependency; load it only when the graph page opens.
const GraphPage = lazy(() => import("./pages/Graph").then((m) => ({ default: m.GraphPage })));

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Overview /> },
      { path: "/rulebook", element: <Rulebook /> },
      { path: "/compliance", element: <Compliance /> },
      {
        path: "/graph",
        element: (
          <Suspense fallback={<LoadingBlock rows={6} />}>
            <GraphPage />
          </Suspense>
        ),
      },
      { path: "/intelligence", element: <Intelligence /> },
      { path: "/findings", element: <Findings /> },
      { path: "/findings/:findingId", element: <FindingDetail /> },
      { path: "/integrity", element: <Integrity /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
