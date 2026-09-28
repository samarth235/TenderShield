import { DatabaseZap, RefreshCw } from "lucide-react";

import { useLoadDemo } from "../lib/hooks";
import { Button, Card, EmptyState } from "./ui";

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
      </EmptyState>
    </Card>
  );
}

export function ErrorCard({ error }: { error: unknown }) {
  return (
    <Card>
      <EmptyState title="Could not reach the backend">
        {error instanceof Error ? error.message : String(error)}. Start the API with <code>make run</code>.
      </EmptyState>
    </Card>
  );
}
