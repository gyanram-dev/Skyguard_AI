import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/common";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/format";
import { useEvaluation } from "@/hooks/useSkyguard";
import type { EvaluationSummary, ModelComparisonEntry, RootCauseEntry } from "@/lib/api";

export const Route = createFileRoute("/_app/evaluation")({
  head: () => ({
    meta: [{ title: "Evaluation | SkyGuard AI" }],
  }),
  component: EvaluationPage,
});

function fmt(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "N/A";
  return value.toFixed(digits);
}

function splitLabel(split: string): string {
  if (split === "test_generalization") return "Out-of-Distribution (OOD)";
  if (split === "test_in_distribution") return "In-Distribution (ID)";
  return split;
}

const METHOD_ORDER = [
  "statistical_zscore",
  "statistical_iqr",
  "isolation_forest",
  "lstm_autoencoder",
  "ensemble",
];

const METHOD_LABELS: Record<string, string> = {
  statistical_zscore: "Statistical (z-score)",
  statistical_iqr: "Statistical (IQR)",
  isolation_forest: "Isolation Forest",
  lstm_autoencoder: "LSTM Autoencoder",
  ensemble: "Ensemble (ens_median)",
};

const RC_CLASSES = ["SPIKE", "FROZEN", "DRIFT", "CROSS", "MIXED", "UNKNOWN"];

function EvaluationPage() {
  const [dataset, setDataset] = useState("delhi");
  const evaluationQuery = useEvaluation();
  const data = evaluationQuery.data;

  const comparison = useMemo(
    () =>
      (data?.model_comparison ?? [])
        .filter((entry) => entry.dataset === dataset)
        .sort((a, b) => METHOD_ORDER.indexOf(a.method) - METHOD_ORDER.indexOf(b.method)),
    [data, dataset],
  );
  const generalization = useMemo(
    () => (data?.generalization ?? []).find((entry) => entry.dataset === dataset),
    [data, dataset],
  );
  const rootCause = useMemo(
    () => (data?.root_cause ?? []).filter((entry) => entry.dataset === dataset),
    [data, dataset],
  );
  const oodDetection = useMemo(
    () =>
      (data?.detection ?? []).find(
        (entry) => entry.dataset === dataset && entry.split === "test_generalization",
      ),
    [data, dataset],
  );

  if (evaluationQuery.isPending) {
    return <LoadingState message="Loading validated benchmark evidence…" />;
  }
  if (evaluationQuery.isError) {
    return (
      <ErrorState
        message={errorMessage(evaluationQuery.error)}
        onRetry={() => evaluationQuery.refetch()}
      />
    );
  }
  if (!data) {
    return (
      <EmptyState
        title="No evaluation evidence"
        message="The API returned no evaluation summary."
      />
    );
  }

  return (
    <>
      <section className="panel flex flex-wrap items-center gap-2 p-3" aria-label="Evidence scope">
        <p className="text-xs font-extrabold">Benchmark Evaluation</p>
        <span className="text-[10px] text-muted-foreground">
          Frozen Phase 6/7/9/10/11 reports plus measured Phase 16 runtime — presented verbatim,
          never recomputed.
        </span>
        <div className="ml-auto flex gap-1.5" role="group" aria-label="Dataset">
          {(["delhi", "jena"] as const).map((option) => (
            <Button
              key={option}
              size="sm"
              variant={dataset === option ? "default" : "outline"}
              onClick={() => setDataset(option)}
              aria-pressed={dataset === option}
              className={cn(dataset !== option && "bg-card")}
            >
              {option === "delhi" ? "Delhi" : "Jena"}
            </Button>
          ))}
        </div>
      </section>

      <SnapshotSection data={data} dataset={dataset} oodDetection={oodDetection} />
      <DetectionSection comparison={comparison} dataset={dataset} />
      {generalization && (
        <GeneralizationSection dataset={dataset} generalization={generalization} />
      )}
      <RootCauseSection rootCause={rootCause} dataset={dataset} />
      <RuntimeSection data={data} />
      <LimitationsSection />
    </>
  );
}

function SnapshotSection({
  data,
  dataset,
  oodDetection,
}: {
  data: EvaluationSummary;
  dataset: string;
  oodDetection: EvaluationSummary["detection"][number] | undefined;
}) {
  const gen = data.generalization.find((entry) => entry.dataset === dataset);
  const rc = data.root_cause.find(
    (entry) => entry.dataset === dataset && entry.split === "test_generalization",
  );
  const runtime = data.runtime;
  const cards = [
    {
      label: "OOD Detection F1",
      value: fmt(oodDetection?.f1),
      hint: "Held-out OOD ensemble",
    },
    {
      label: "OOD Event Recall",
      value: fmt(gen?.ood_event_recall),
      hint: "Injected events detected",
    },
    {
      label: "RC Unknown Rate (OOD)",
      value: fmt(rc?.unknown_rate),
      hint: "Diagnosis withheld share",
    },
    {
      label: "Measured Throughput",
      value:
        typeof runtime["throughput_rows_per_s"] === "number"
          ? `${(runtime["throughput_rows_per_s"] as number).toFixed(1)} rows/s`
          : "N/A",
      hint: "Single-machine replay",
    },
  ];
  return (
    <section className="panel p-4" aria-label="System snapshot">
      <p className="section-kicker">System snapshot · {dataset === "delhi" ? "Delhi" : "Jena"}</p>
      <div className="mt-2 grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        {cards.map((card) => (
          <article key={card.label} className="metric-card">
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground">{card.label}</p>
              <p className="text-lg font-extrabold leading-tight">{card.value}</p>
              <p className="text-[9px] text-muted-foreground">{card.hint}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function DetectionSection({
  comparison,
  dataset,
}: {
  comparison: ModelComparisonEntry[];
  dataset: string;
}) {
  const rows: Array<{ label: string; get: (entry: ModelComparisonEntry) => string }> = [
    { label: "Precision", get: (entry) => fmt(entry.precision) },
    { label: "Recall", get: (entry) => fmt(entry.recall) },
    { label: "F1", get: (entry) => fmt(entry.f1) },
    { label: "Event Recall", get: (entry) => fmt(entry.event_recall) },
    { label: "FPR", get: (entry) => fmt(entry.fpr) },
  ];
  const splits = ["test_in_distribution", "test_generalization"];
  return (
    <section className="panel p-4" aria-label="Detection evidence">
      <p className="section-kicker">
        Detection evidence · {dataset === "delhi" ? "Delhi" : "Jena"}
      </p>
      <h2 className="mt-1 text-lg font-extrabold">Approach comparison</h2>
      <p className="mt-0.5 text-[10px] text-muted-foreground">
        Row-level benchmark metrics per approach. Event recall is measured for the ensemble only;
        reference approaches show N/A where unmeasured — not inferred. No ranking is implied.
      </p>
      {splits.map((split) => {
        const cols = comparison.filter((entry) => entry.split === split);
        if (cols.length === 0) return null;
        return (
          <div key={split} className="mt-3 overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-[560px] text-[11px]">
              <caption className="px-3 py-2 text-left text-[10px] font-extrabold uppercase tracking-[0.06em]">
                {splitLabel(split)}
              </caption>
              <thead>
                <tr className="border-t border-border text-muted-foreground">
                  <th className="px-3 py-1.5 text-left font-semibold">Metric</th>
                  {cols.map((entry) => (
                    <th key={entry.method} className="px-3 py-1.5 text-right font-semibold">
                      {METHOD_LABELS[entry.method] ?? entry.method}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.label} className="border-t border-border">
                    <td className="px-3 py-1.5 font-bold">{row.label}</td>
                    {cols.map((entry) => (
                      <td key={entry.method} className="px-3 py-1.5 text-right tabular-nums">
                        {row.get(entry)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </section>
  );
}

function GeneralizationSection({
  dataset,
  generalization,
}: {
  dataset: string;
  generalization: EvaluationSummary["generalization"][number];
}) {
  const cards = [
    { label: "ID F1", value: fmt(generalization.id_f1) },
    { label: "OOD F1", value: fmt(generalization.ood_f1) },
    { label: "ID Event Recall", value: fmt(generalization.id_event_recall) },
    { label: "OOD Event Recall", value: fmt(generalization.ood_event_recall) },
  ];
  return (
    <section className="panel p-4" aria-label="Generalization">
      <p className="section-kicker">Generalization · {dataset === "delhi" ? "Delhi" : "Jena"}</p>
      <h2 className="mt-1 text-lg font-extrabold">Held-out OOD behavior</h2>
      <p className="mt-0.5 text-[10px] text-muted-foreground">
        Evaluated on held-out anomaly conditions not used for training. OOD is a benchmark split,
        not another live stream.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        {cards.map((card) => (
          <article key={card.label} className="metric-card">
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground">{card.label}</p>
              <p className="text-lg font-extrabold leading-tight">{card.value}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function RootCauseSection({
  rootCause,
  dataset,
}: {
  rootCause: RootCauseEntry[];
  dataset: string;
}) {
  return (
    <section className="panel p-4" aria-label="Root cause evidence">
      <p className="section-kicker">Root cause · {dataset === "delhi" ? "Delhi" : "Jena"}</p>
      <h2 className="mt-1 text-lg font-extrabold">Diagnosis evidence</h2>
      <p className="mt-0.5 text-[10px] text-muted-foreground">
        Root-cause diagnosis is a model estimate, not certainty — accuracy varies by fault type and
        degrades on OOD conditions. Weak cases are shown, not hidden.
      </p>
      {rootCause.map((entry) => (
        <div key={entry.split} className="mt-3 overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[560px] text-[11px]">
            <caption className="px-3 py-2 text-left text-[10px] font-extrabold uppercase tracking-[0.06em]">
              {splitLabel(entry.split)} · {entry.n_diagnosed} diagnosed · accuracy{" "}
              {fmt(entry.accuracy_incl_unknown)} incl. unknown / {fmt(entry.accuracy_excl_unknown)}{" "}
              excl. unknown · unknown rate {fmt(entry.unknown_rate)} · macro F1{" "}
              {fmt(entry.macro_f1)}
            </caption>
            <thead>
              <tr className="border-t border-border text-muted-foreground">
                <th className="px-3 py-1.5 text-left font-semibold">Class</th>
                <th className="px-3 py-1.5 text-right font-semibold">Support</th>
                <th className="px-3 py-1.5 text-right font-semibold">Precision</th>
                <th className="px-3 py-1.5 text-right font-semibold">Recall</th>
                <th className="px-3 py-1.5 text-right font-semibold">F1</th>
              </tr>
            </thead>
            <tbody>
              {RC_CLASSES.map((cls) => {
                const stats = entry.per_class[cls];
                return (
                  <tr key={cls} className="border-t border-border">
                    <td className="px-3 py-1.5 font-bold">{cls}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {stats?.support ?? "N/A"}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(stats?.precision)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(stats?.recall)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(stats?.f1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}

function RuntimeSection({ data }: { data: EvaluationSummary }) {
  const runtime = data.runtime;
  const perReading = runtime["per_reading_s"] as { median?: number; p95?: number } | undefined;
  const rows: Array<[string, string]> = [
    ["Connection (warm)", num(runtime["connection_latency_s_warm"], "s")],
    ["Per-reading median", num(perReading?.median, "s")],
    ["Per-reading p95", num(perReading?.p95, "s")],
    [
      "Replay throughput",
      typeof runtime["throughput_rows_per_s"] === "number"
        ? `${(runtime["throughput_rows_per_s"] as number).toFixed(1)} rows/s`
        : "N/A",
    ],
    ["300-row sample", num(runtime["sample_300_rows_s"], "s")],
    ["Cold model load", num(runtime["cold_model_load_s"], "s")],
    ["Requested speed", num(runtime["requested_speed"], "×", 0)],
    ["Effective speed", num(runtime["effective_speed"], "×", 0)],
  ];
  return (
    <section className="panel p-4" aria-label="Runtime performance">
      <p className="section-kicker">Measured system performance</p>
      <h2 className="mt-1 text-lg font-extrabold">Runtime evidence</h2>
      <p className="mt-0.5 text-[10px] text-muted-foreground">
        Single-machine live measurements (methodology in provenance), not vendor claims. Requested
        3600× could not be fully sustained — the engine reported the achieved effective speed
        instead; anomalous rows involving LSTM/SHAP reduce playback speed.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        {rows.map(([label, value]) => (
          <article key={label} className="metric-card">
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground">{label}</p>
              <p className="text-lg font-extrabold leading-tight">{value}</p>
            </div>
          </article>
        ))}
      </div>
      <p className="mt-2 text-[10px] text-muted-foreground">
        Provenance: {String(data.provenance["runtime"] ?? "reports/replay/performance.json")} ·
        measured {String((runtime["measured_at"] as string | undefined) ?? "—")}.
      </p>
    </section>
  );
}

function num(value: unknown, unit: string, digits = 2): string {
  if (typeof value !== "number") return "N/A";
  return `${value.toFixed(digits)}${unit}`;
}

function LimitationsSection() {
  const items = [
    "Benchmark faults are controlled and injected — not naturally occurring failures.",
    "Replay is accelerated historical data, not a physical live AWS connection.",
    "Root-cause performance varies by fault type and degrades on OOD conditions.",
    "LSTM/SHAP computation can increase per-reading inference latency.",
    "Replay currently supports detector-covered stations (DEL-01, JENA-01).",
    "NOAA spatial data is contextual evidence, not ground truth.",
  ];
  return (
    <section className="panel p-4" aria-label="Limitations">
      <p className="section-kicker">Limitations</p>
      <h2 className="mt-1 text-lg font-extrabold">What this evidence does not claim</h2>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-[11px] text-muted-foreground">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] text-muted-foreground">
        Live/replay observations and benchmark evaluation metrics represent different things and are
        labeled separately: Historical Replay vs Benchmark Evaluation vs Held-out OOD.
      </p>
    </section>
  );
}
