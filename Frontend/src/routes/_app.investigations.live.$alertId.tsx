import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DetailStat, EmptyState, ErrorState, FactRow, LoadingState } from "@/components/common";
import { HistoryChart, toChartPoints } from "@/components/charts";
import { EvidenceList } from "@/components/evidence";
import { errorMessage, formatDateTime, formatScore } from "@/lib/format";
import { useLiveAlert } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/investigations/live/$alertId")({
  head: ({ params }) => ({
    meta: [{ title: `Live Investigation ${params.alertId} | SkyGuard AI` }],
  }),
  component: LiveInvestigationPage,
});

function LiveInvestigationPage() {
  const { alertId } = Route.useParams();
  const navigate = useNavigate();
  const detailQuery = useLiveAlert(alertId);
  const detail = detailQuery.data;

  if (detailQuery.isPending) return <LoadingState message="Loading live investigation…" />;
  if (detailQuery.isError) {
    return <ErrorState message={errorMessage(detailQuery.error)} onRetry={() => detailQuery.refetch()} />;
  }
  if (!detail) {
    return <EmptyState title="Live investigation unavailable" message="No persisted episode payload was found." />;
  }

  const episode = detail.episode;
  const latest = detail.observations.at(-1);
  const history = detail.observations.map((row) => ({
    timestamp: row.timestamp,
    temperature: row.temperature_c,
  }));
  const evidence = Object.entries(detail.evidence).map(([source, value]) => ({
    title: source.replaceAll("_", " "),
    detail: typeof value === "string" ? value : JSON.stringify(value),
    source,
  }));

  return (
    <>
      <section className="panel p-4" aria-label="Live investigation">
        <p className="section-kicker">LIVE_ALERT · {episode.station_id}</p>
        <h1 className="mt-1 text-lg font-extrabold">{episode.interpretation}</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Detected {formatDateTime(episode.started_at)}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <DetailStat label="Episode score" value={formatScore(episode.score)} emphasis />
          <DetailStat label="Current state" value={episode.status} />
          <DetailStat label="Detections" value={String(episode.detection_count)} />
          <DetailStat label="Data quality" value={latest?.dq_state ?? "Not retained"} />
        </div>
      </section>

      <section className="panel p-4" aria-label="Live observation history">
        <p className="section-kicker">Causal station history · temperature</p>
        <HistoryChart
          data={toChartPoints(history, "temperature")}
          height={180}
          ariaLabel={`Live temperature history for ${episode.station_id}`}
        />
        <div className="mt-2 divide-y divide-border">
          <FactRow label="Source" value={latest?.source ?? "Not retained"} />
          <FactRow label="Pressure basis" value={latest?.pressure_basis ?? "Not retained"} />
          <FactRow label="Last observation" value={formatDateTime(episode.last_seen_at)} />
          <FactRow label="Provenance" value="Canonical observation persisted by the live adapter" />
        </div>
      </section>

      <section className="panel p-4" aria-label="Stored inference evidence">
        <EvidenceList evidence={evidence} loading={false} />
      </section>

      <section className="panel p-4" aria-label="Operator action">
        <p className="section-kicker">Recommended operator action</p>
        <p className="mt-1 text-sm">
          Review the stored observation and compare it with nearby station context before dispatch.
        </p>
      </section>

      <Button variant="outline" size="sm" onClick={() => navigate({ to: "/live" })}>
        <ArrowLeft />
        Back to Live
      </Button>
    </>
  );
}