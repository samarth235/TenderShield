import { DatabaseZap, RefreshCw, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

import { ApiError } from "../api/client";
import { useLoadDemo } from "../lib/hooks";
import { Button, Card, EmptyState, LoadingBlock } from "./ui";

export function NotLoaded({ what }: { what: string }) {
  const load = useLoadDemo();
  return (
    <Card>
      <EmptyState
        icon={<DatabaseZap size={30} />}
        title={`No ${what} yet`}
        action={
          <Button variant="brand" icon={<RefreshCw size={15} />} loading={load.isPending} onClick={() => load.mutate()}>
            Load demonstration tender
          </Button>
        }
      >
        Load the preloaded demonstration tender (TN-2026-014). The backend analyses it end to end in about a second.
        {load.isError && (
          <span style={{ display: "block", marginTop: 8, color: "var(--fail)" }}>
            {load.error instanceof Error ? load.error.message : String(load.error)}
          </span>
        )}
      </EmptyState>
    </Card>
  );
}

// 502/503/504 come from the dev proxy when nothing is listening on the API port.
const unreachable = (error: unknown) =>
  error instanceof TypeError || (error instanceof ApiError && [502, 503, 504].includes(error.status));

export function ErrorCard({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  if (unreachable(error))
    return (
      <Card>
        <EmptyState title="Could not reach the backend">
          {message}. Start the API with <code>make run</code>.
        </EmptyState>
      </Card>
    );
  return (
    <Card>
      <EmptyState icon={<TriangleAlert size={30} />} title="The backend returned an error">
        {error instanceof ApiError ? `${error.status} · ${message}` : message}
      </EmptyState>
    </Card>
  );
}

// A lazily loaded page chunk fails to import when the dev server restarted or a new build was deployed.
const CHUNK_ERROR = /dynamically imported module|Importing a module script failed|error loading dynamically imported module/i;
const RELOAD_KEY = "ts-chunk-reload-at";

/** Reload at most once every 10 s so a server that is really down cannot cause a reload loop. */
function reloadOnce(): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0);
    if (Date.now() - last < 10_000) return false;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch {
    return false;
  }
  location.reload();
  return true;
}

/** Route-level error boundary: keeps the sidebar visible and offers a way out. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : String(error);
  const chunk = CHUNK_ERROR.test(message);
  const [reloading, setReloading] = useState(chunk);

  useEffect(() => {
    if (chunk && !reloadOnce()) setReloading(false);
  }, [chunk]);

  if (reloading) return <LoadingBlock rows={6} />;
  return (
    <Card>
      <EmptyState
        icon={<TriangleAlert size={30} />}
        title={chunk ? "This page could not be loaded" : "Something went wrong on this page"}
        action={
          <Button variant="brand" icon={<RefreshCw size={15} />} onClick={() => location.reload()}>
            Reload page
          </Button>
        }
      >
        {chunk ? "The frontend dev server restarted or moved to another port. Check the URL printed by npm run dev, then reload." : message}
      </EmptyState>
    </Card>
  );
}
