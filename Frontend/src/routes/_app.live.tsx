import { Link, createFileRoute } from "@tanstack/react-router";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, FactRow, LoadingState } from "@/components/common";
import { errorMessage, formatDateTime } from "@/lib/format";
import {
  useLiveAlerts,
  useLiveStations,
  useLiveStatus,
  useStartLive,
  useStartLiveDemo,
  useStopLive,
} from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/live")({
  head: () => ({
    meta: [{ title: "Live | SkyGuard AI" }],
  }),
  component: LivePage,
});

function modeLabel(mode: string): string {
  if (mode === "LIVE_IMD") return "IMD LIVE";
  if (mode === "CONTROLLED_LIVE") return "CONTROLLED LIVE";
  if (mode === "LIVE_ARG") return "ARG LIVE";
  return "OFFLINE";
}

function LivePage() {
  const status = useLiveStatus();
  const stations = useLiveStations();
  const alerts = useLiveAlerts();
  const startProvider = useStartLive();
  const startDemo = useStartLiveDemo();
  const stop = useStopLive();

  if (status.isPending) return <LoadingState message="Loading live state…" />;
  if (status.isError)
    return <ErrorState message={errorMessage(status.error)} onRetry={() => status.refetch()} />;

  const state = status.data;
  return (
    <div className="space-y-3">
      <div className="panel p-4">
        <p className="section-kicker">Live ingestion</p>
        <div className="mt-1 flex items-center gap-2">
          <h1 className="text-lg font-extrabold">{modeLabel(state.mode)}</h1>
          <span className="text-[10px] font-bold uppercase text-muted-foreground">
            {state.provider_status}
          </span>
        </div>
        {state.state === "LIVE_UNAVAILABLE" ? (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            {state.detail ?? "Live IMD connection unavailable — no readings are synthesized."}
          </p>
        ) : (
          <div className="mt-2 divide-y divide-border">
            <FactRow label="Source" value={state.source ?? "—"} />
            <FactRow label="Last successful fetch" value={formatDateTime(state.last_success)} />
            <FactRow label="Open episodes" value={String(state.open_episodes)} />
            {state.last_error ? <FactRow label="Last error" value={state.last_error} /> : null}
          </div>
        )}
        <div className="mt-2 flex gap-2">
          <Button
            size="sm"
            disabled={state.mode !== "LIVE_IMD" || startProvider.isPending}
            onClick={() => startProvider.mutate(undefined, { onSuccess: () => status.refetch() })}
          >
            Start configured provider
          </Button>
          <Button
            size="sm"
            disabled={startDemo.isPending}
            onClick={() => startDemo.mutate(undefined, { onSuccess: () => status.refetch() })}
          >
            Start controlled live demo
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={stop.isPending}
            onClick={() => stop.mutate(undefined, { onSuccess: () => status.refetch() })}
          >
            Stop
          </Button>
        </div>
        {state.mode === "CONTROLLED_LIVE" ? (
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            CONTROLLED LIVE DEMO — scripted observations, not IMD data.
          </p>
        ) : null}
      </div>

      <div className="panel p-4">
        <p className="section-kicker">Live stations</p>
        {stations.isPending ? (
          <LoadingState message="Loading stations…" />
        ) : stations.isError || !stations.data ? (
          <ErrorState message={errorMessage(stations.error)} onRetry={() => stations.refetch()} />
        ) : stations.data.stations.length === 0 ? (
          <EmptyState
            title={state.status === "NOT_CONFIGURED" ? "LIVE UNAVAILABLE" : "No observations yet"}
            message={
              state.status === "NOT_CONFIGURED"
                ? "Configure the provider endpoint before starting live ingestion."
                : state.status === "CONNECTION_FAILED"
                  ? "The configured provider could not be reached. No readings are synthesized."
                  : "No live observations have been received."
            }
          />
        ) : (
          <div className="mt-1 divide-y divide-border">
            {stations.data.stations.map((station) => (
              <FactRow
                key={station.station_id}
                label={`${station.station_id} · ${station.warm_state} · ${station.history_rows} rows`}
                value={station.latest_timestamp ?? "—"}
              />
            ))}
          </div>
        )}
      </div>

      <div className="panel p-4">
        <p className="section-kicker">Live alert episodes (operational — separate from replay)</p>
        {alerts.isPending ? (
          <LoadingState message="Loading episodes…" />
        ) : alerts.isError || !alerts.data ? (
          <ErrorState message={errorMessage(alerts.error)} onRetry={() => alerts.refetch()} />
        ) : alerts.data.episodes.length === 0 ? (
          <EmptyState title="No live episodes" message="Anomalous live runs group here." />
        ) : (
          <div className="mt-1 divide-y divide-border">
            {alerts.data.episodes.map((episode) => (
              <div key={episode.alert_id} className="flex items-center gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <FactRow
                    label={`${episode.station_id} · ${episode.interpretation} · ×${episode.detection_count}`}
                    value={episode.status}
                  />
                </div>
                <Link
                  to="/investigations/live/$alertId"
                  params={{ alertId: episode.alert_id }}
                  className="shrink-0 text-xs font-bold text-foreground underline underline-offset-4"
                >
                  Open investigation
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
