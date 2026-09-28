import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowLeft, Eye, FlaskConical, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DetailStat, ErrorState, FactRow, StatusBadge } from "@/components/common";
import { EvidenceList } from "@/components/evidence";
import { ApiError } from "@/lib/api";
import type { ConfirmUploadPayload, UploadAnalysisResult, UploadAnomalyRecord } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import { useUploadSession } from "@/components/upload/UploadSessionContext";
import { confirmUpload, runUploadAnalysis, uploadCsv } from "@/lib/api";

export const Route = createFileRoute("/_app/analyze-data")({
  head: () => ({
    meta: [{ title: "Analyze Data | SkyGuard AI" }],
  }),
  component: AnalyzeDataPage,
});

const FIELD_DEFS = [
  { field: "timestamp", label: "Timestamp", required: true },
  { field: "temperature", label: "Temperature", required: true },
  { field: "humidity", label: "Relative Humidity", required: false },
  { field: "pressure", label: "Pressure", required: false },
] as const;

function AnalyzeDataPage() {
  const {
    session,
    preview,
    result,
    selectedAnomaly,
    setSession,
    setPreview,
    setResult,
    setSelectedAnomaly,
    reset,
  } = useUploadSession();
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<"idle" | "working" | "error">("idle");
  const [failure, setFailure] = useState<string | null>(null);
  const [fieldMap, setFieldMap] = useState<Record<string, string>>({});
  const [tempUnit, setTempUnit] = useState("");
  const [presUnit, setPresUnit] = useState("");
  const [stationLabel, setStationLabel] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const step = selectedAnomaly
    ? "detail"
    : result
      ? "results"
      : preview
        ? "preview"
        : session
          ? "mapping"
          : "upload";

  const fail = (error: unknown) => {
    const message =
      error instanceof ApiError && error.code
        ? `${errorMessage(error)} (code: ${error.code})`
        : errorMessage(error);
    setFailure(message);
    setPhase("error");
  };

  const doUpload = async () => {
    if (!file) return;
    setPhase("working");
    setFailure(null);
    try {
      reset();
      const response = await uploadCsv(file);
      setSession(response);
      const initial: Record<string, string> = {};
      for (const def of FIELD_DEFS) {
        const proposed = response.mapping[def.field]?.column;
        if (proposed) initial[def.field] = proposed;
      }
      setFieldMap(initial);
      setTempUnit(response.units["temperature"]?.unit ?? "");
      setPresUnit(response.units["pressure"]?.unit ?? "");
      setStationLabel("");
      setPhase("idle");
    } catch (error) {
      fail(error);
    }
  };

  const doConfirm = async () => {
    if (!session) return;
    if (!fieldMap["timestamp"] || !fieldMap["temperature"]) {
      setFormError("Timestamp and Temperature columns are required.");
      return;
    }
    if (!tempUnit) {
      setFormError("Select the temperature unit.");
      return;
    }
    if (fieldMap["pressure"] && !presUnit) {
      setFormError("Select the pressure unit.");
      return;
    }
    setFormError(null);
    setPhase("working");
    setFailure(null);
    try {
      const payload: ConfirmUploadPayload = {
        mapping: {
          timestamp: fieldMap["timestamp"] as string,
          temperature: fieldMap["temperature"] as string,
          humidity: fieldMap["humidity"] ?? null,
          pressure: fieldMap["pressure"] ?? null,
        },
        units: { temperature: tempUnit, pressure: presUnit || null },
        station_label: stationLabel.trim() === "" ? undefined : stationLabel.trim(),
      };
      setPreview(await confirmUpload(session.session_id, payload));
      setPhase("idle");
    } catch (error) {
      fail(error);
    }
  };

  const doRun = async () => {
    if (!session) return;
    setPhase("working");
    setFailure(null);
    try {
      setResult(await runUploadAnalysis(session.session_id));
      setPhase("idle");
    } catch (error) {
      fail(error);
    }
  };

  return (
    <>
      {step === "upload" && (
        <UploadStep
          file={file}
          setFile={setFile}
          phase={phase}
          failure={failure}
          onUpload={doUpload}
        />
      )}
      {step === "mapping" && session && (
        <MappingStep
          sessionId={session.session_id}
          filename={session.filename}
          sizeBytes={session.size_bytes}
          rows={session.rows}
          columns={session.columns}
          proposals={session.mapping}
          unitProposals={session.units}
          warnings={session.warnings}
          fieldMap={fieldMap}
          setFieldMap={setFieldMap}
          tempUnit={tempUnit}
          setTempUnit={setTempUnit}
          presUnit={presUnit}
          setPresUnit={setPresUnit}
          stationLabel={stationLabel}
          setStationLabel={setStationLabel}
          formError={formError}
          phase={phase}
          failure={failure}
          onConfirm={doConfirm}
          onRestart={reset}
        />
      )}
      {step === "preview" && preview && (
        <PreviewStep
          preview={preview}
          phase={phase}
          failure={failure}
          onRun={doRun}
          onEditMapping={() => setPreview(null)}
        />
      )}
      {step === "results" && result && (
        <ResultsStep result={result} onReview={setSelectedAnomaly} onNewUpload={reset} />
      )}
      {step === "detail" && selectedAnomaly && (
        <AnomalyDetail anomaly={selectedAnomaly} onBack={() => setSelectedAnomaly(null)} />
      )}
    </>
  );
}

function UploadStep({
  file,
  setFile,
  phase,
  failure,
  onUpload,
}: {
  file: File | null;
  setFile: (file: File | null) => void;
  phase: string;
  failure: string | null;
  onUpload: () => void;
}) {
  return (
    <section className="panel p-4" aria-label="Upload station CSV">
      <p className="section-kicker">Analyze New Station Data</p>
      <h2 className="mt-1 text-lg font-extrabold">Upload station CSV</h2>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        The file is processed by the SkyGuard backend — never sent anywhere else. Limits: 10 MB,
        200,000 rows, 50 columns. Minimum: timestamp + temperature.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Input
          type="file"
          accept=".csv"
          aria-label="Station CSV file"
          className="max-w-xs cursor-pointer"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <Button size="sm" onClick={onUpload} disabled={!file || phase === "working"}>
          <Upload />
          {phase === "working" ? "Uploading…" : "Upload"}
        </Button>
      </div>
      {file && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          {file.name} · {(file.size / 1024).toFixed(1)} KB
        </p>
      )}
      {phase === "working" && (
        <p className="mt-2 text-[11px] text-muted-foreground" role="status">
          Parsing and proposing column mapping…
        </p>
      )}
      {phase === "error" && failure && (
        <div className="mt-2">
          <ErrorState message={failure} />
        </div>
      )}
    </section>
  );
}

const NOT_MAPPED = "__none__";

function MappingStep(props: {
  sessionId: string;
  filename: string;
  sizeBytes: number;
  rows: number;
  columns: string[];
  proposals: Record<string, { column: string | null; confidence: string; alternates: string[] }>;
  unitProposals: Record<string, { unit: string | null; source: string }>;
  warnings: string[];
  fieldMap: Record<string, string>;
  setFieldMap: (map: Record<string, string>) => void;
  tempUnit: string;
  setTempUnit: (unit: string) => void;
  presUnit: string;
  setPresUnit: (unit: string) => void;
  stationLabel: string;
  setStationLabel: (label: string) => void;
  formError: string | null;
  phase: string;
  failure: string | null;
  onConfirm: () => void;
  onRestart: () => void;
}) {
  const setField = (field: string, value: string) => {
    const next = { ...props.fieldMap };
    if (value === NOT_MAPPED) delete next[field];
    else next[field] = value;
    props.setFieldMap(next);
  };
  return (
    <section className="panel p-4" aria-label="Confirm column mapping">
      <p className="section-kicker">CSV column → SkyGuard field</p>
      <h2 className="mt-1 text-lg font-extrabold">Confirm mapping</h2>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {props.filename} · {(props.sizeBytes / 1024).toFixed(1)} KB · {props.rows} rows ·{" "}
        {props.columns.length} columns. Review each proposal before analysis.
      </p>
      {props.warnings.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-[11px] text-muted-foreground">
          {props.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        {FIELD_DEFS.map((def) => {
          const proposal = props.proposals[def.field];
          return (
            <div key={def.field} className="space-y-1.5">
              <Label htmlFor={`map-${def.field}`}>
                {def.label} {def.required ? "(required)" : "(optional)"}
              </Label>
              <Select
                value={props.fieldMap[def.field] ?? NOT_MAPPED}
                onValueChange={(value) => setField(def.field, value)}
              >
                <SelectTrigger id={`map-${def.field}`} aria-label={`${def.label} column`}>
                  <SelectValue placeholder={def.required ? "Select column" : "Not mapped"} />
                </SelectTrigger>
                <SelectContent>
                  {!def.required && <SelectItem value={NOT_MAPPED}>Not mapped</SelectItem>}
                  {props.columns.map((column) => (
                    <SelectItem key={column} value={column}>
                      {column}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-muted-foreground">
                Proposal: {proposal?.column ?? "none"} ({proposal?.confidence ?? "absent"})
                {proposal &&
                  proposal.alternates.length > 0 &&
                  ` — alternates: ${proposal.alternates.join(", ")}`}
              </p>
            </div>
          );
        })}
        <div className="space-y-1.5">
          <Label htmlFor="unit-temp">Temperature unit</Label>
          <Select value={props.tempUnit} onValueChange={props.setTempUnit}>
            <SelectTrigger id="unit-temp" aria-label="Temperature unit">
              <SelectValue placeholder="Select unit" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="C">°C</SelectItem>
              <SelectItem value="F">°F</SelectItem>
            </SelectContent>
          </Select>
          <UnitHint proposal={props.unitProposals["temperature"]} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="unit-pres">Pressure unit</Label>
          <Select
            value={props.presUnit}
            onValueChange={props.setPresUnit}
            disabled={!props.fieldMap["pressure"]}
          >
            <SelectTrigger id="unit-pres" aria-label="Pressure unit">
              <SelectValue placeholder="Select unit" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="hPa">hPa</SelectItem>
              <SelectItem value="Pa">Pa</SelectItem>
            </SelectContent>
          </Select>
          <UnitHint proposal={props.unitProposals["pressure"]} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="station-label">Station name/ID (optional)</Label>
          <Input
            id="station-label"
            value={props.stationLabel}
            placeholder="New Uploaded Station"
            onChange={(event) => props.setStationLabel(event.target.value)}
          />
        </div>
      </div>
      {props.formError && (
        <p className="mt-2 text-[11px] font-semibold text-anomaly-deep" role="alert">
          {props.formError}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" onClick={props.onConfirm} disabled={props.phase === "working"}>
          <FlaskConical />
          {props.phase === "working" ? "Validating…" : "Validate & preview quality"}
        </Button>
        <Button size="sm" variant="outline" onClick={props.onRestart}>
          New upload
        </Button>
      </div>
      {props.phase === "error" && props.failure && (
        <div className="mt-2">
          <ErrorState message={props.failure} />
        </div>
      )}
    </section>
  );
}

function UnitHint({ proposal }: { proposal: { unit: string | null; source: string } | undefined }) {
  if (!proposal) return null;
  const text =
    proposal.source === "inferred"
      ? `Detected: ${proposal.unit} (from column name — confirm it).`
      : proposal.source === "ask"
        ? "Unit could not be inferred — select it explicitly."
        : "Unit not applicable.";
  return <p className="text-[10px] text-muted-foreground">{text}</p>;
}

function PreviewStep({
  preview,
  phase,
  failure,
  onRun,
  onEditMapping,
}: {
  preview: {
    station_label: string;
    rows: number;
    time_range: { start: string | null; end: string | null };
    cadence_min: number;
    duplicates: number;
    missing: Record<string, number>;
    large_gaps: number;
    invalid_timestamps: number;
    non_finite: number;
    rh_invalid: number | null;
    rh_available: boolean;
    pressure_available: boolean;
    ml_eligible: number;
    quality_counts: Record<string, number>;
  };
  phase: string;
  failure: string | null;
  onRun: () => void;
  onEditMapping: () => void;
}) {
  const facts: Array<[string, string]> = [
    ["Rows", String(preview.rows)],
    ["Time range", `${preview.time_range.start ?? "—"} → ${preview.time_range.end ?? "—"}`],
    ["Sampling interval", `${preview.cadence_min} min`],
    ["Duplicates", String(preview.duplicates)],
    ["Missing temperature", String(preview.missing["temperature"] ?? 0)],
    [
      "Missing humidity",
      preview.rh_available ? String(preview.missing["humidity"] ?? 0) : "column absent",
    ],
    [
      "Missing pressure",
      preview.pressure_available ? String(preview.missing["pressure"] ?? 0) : "column absent",
    ],
    ["Large gaps", String(preview.large_gaps)],
    ["Invalid timestamps", String(preview.invalid_timestamps)],
    ["Non-finite values", String(preview.non_finite)],
    [
      "RH validity",
      preview.rh_available ? `${preview.rh_invalid ?? 0} out of range` : "column absent",
    ],
    ["ML-eligible rows", String(preview.ml_eligible)],
  ];
  return (
    <section className="panel p-4" aria-label="Data quality preview">
      <p className="section-kicker">Data quality preview · {preview.station_label}</p>
      <h2 className="mt-1 text-lg font-extrabold">Dataset summary</h2>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        Quality screening only — unusual values are not anomalies. Missing humidity or pressure
        leaves the corresponding evidence unavailable, never fabricated.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2 xl:grid-cols-4">
        {facts.map(([label, value]) => (
          <DetailStat key={label} label={label} value={value} tone="bg-surface-blue-tint" />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" onClick={onRun} disabled={phase === "working"}>
          <FlaskConical />
          {phase === "working" ? "Analyzing…" : "Run analysis"}
        </Button>
        <Button size="sm" variant="outline" onClick={onEditMapping}>
          Edit mapping
        </Button>
      </div>
      {phase === "error" && failure && (
        <div className="mt-2">
          <ErrorState message={failure} />
        </div>
      )}
    </section>
  );
}

function ResultsStep({
  result,
  onReview,
  onNewUpload,
}: {
  result: UploadAnalysisResult;
  onReview: (anomaly: UploadAnomalyRecord) => void;
  onNewUpload: () => void;
}) {
  const present = Object.entries(result.breakdown).filter(([, count]) => count > 0);
  return (
    <>
      <section className="panel p-4" aria-label="New station analysis">
        <p className="section-kicker">New Station Analysis</p>
        <h2 className="mt-1 text-lg font-extrabold">
          {result.station_label} · {result.filename}
        </h2>
        <div className="mt-2 grid grid-cols-2 gap-2 xl:grid-cols-4">
          <DetailStat label="Observations" value={String(result.observations)} emphasis />
          <DetailStat label="Normal" value={String(result.normal)} tone="bg-success-soft" />
          <DetailStat
            label="Anomalies"
            value={String(result.anomalies)}
            tone="bg-anomaly-soft"
            valueTone="text-anomaly"
          />
          <DetailStat
            label="Data-quality events"
            value={String(result.dq_events)}
            tone="bg-surface-blue-tint"
          />
        </div>
        {present.length > 0 && (
          <div className="mt-3">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
              Anomaly breakdown
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {present.map(([estimate, count]) => (
                <span
                  key={estimate}
                  className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-bold"
                >
                  {estimate} · {count}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="mt-3">
          <Button size="sm" variant="outline" onClick={onNewUpload}>
            <Upload />
            New upload
          </Button>
        </div>
      </section>

      <section className="panel p-4" aria-label="Detected anomalies">
        <p className="section-kicker">Anomalies · {result.anomalies}</p>
        {result.anomalies_detail.length === 0 ? (
          <p className="mt-2 text-[11px] text-muted-foreground" role="status">
            No anomalies detected in this dataset.
          </p>
        ) : (
          <div className="mt-2 overflow-x-auto rounded-xl border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                  <TableHead className="text-right">Confidence</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Review</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.anomalies_detail.map((anomaly) => (
                  <TableRow key={`${anomaly.timestamp}-${anomaly.score ?? "na"}`}>
                    <TableCell className="font-semibold">{anomaly.timestamp}</TableCell>
                    <TableCell className="font-extrabold">{anomaly.root_cause_estimate}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {anomaly.score !== null && anomaly.score !== undefined
                        ? anomaly.score.toFixed(2)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">—</TableCell>
                    <TableCell>
                      <StatusBadge
                        status={anomaly.root_cause_estimate === "UNKNOWN" ? "review" : "anomaly"}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="outline" onClick={() => onReview(anomaly)}>
                        <Eye />
                        Review
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </>
  );
}

function AnomalyDetail({ anomaly, onBack }: { anomaly: UploadAnomalyRecord; onBack: () => void }) {
  const evidence = anomaly.evidence as {
    statistical?: { max_abs_z?: number | null; threshold?: number; reason?: string };
    temporal?: { cadence_min?: number; frozen?: boolean };
    multivariate?: { max_abs_robust_deviation_2h?: number | null };
    data_quality?: { status?: string; ml_eligible?: boolean };
    ml_models?: { available?: boolean; reason?: string };
    spatial?: { available?: boolean; reason?: string };
  };
  const items = [
    {
      title: "Statistical evidence",
      detail: `max|z|=${evidence.statistical?.max_abs_z?.toFixed(2) ?? "—"} vs threshold ${evidence.statistical?.threshold ?? "—"} (${evidence.statistical?.reason ?? "statistical baseline"}).`,
      source: "statistical",
    },
    {
      title: "Temporal evidence",
      detail: `Evaluated in causal order at ${evidence.temporal?.cadence_min ?? "—"}-minute cadence${evidence.temporal?.frozen ? " with frozen-signal flags" : ""}.`,
      source: "temporal",
    },
    {
      title: "Multivariate evidence",
      detail:
        typeof evidence.multivariate?.max_abs_robust_deviation_2h === "number"
          ? `Max robust deviation ${(evidence.multivariate?.max_abs_robust_deviation_2h as number).toFixed(2)}.`
          : "Multivariate context unavailable for this event.",
      source: "multivariate",
    },
    {
      title: "ML evidence",
      detail:
        evidence.ml_models?.available === true
          ? "Trained-model evidence available."
          : (evidence.ml_models?.reason ??
            "Delhi/Jena-trained detectors are not validated for unseen stations."),
      source: "ml",
    },
    {
      title: "Spatial evidence",
      detail:
        evidence.spatial?.available === true
          ? "Spatial context available."
          : (evidence.spatial?.reason ?? "No neighbor context for an unseen station."),
      source: "spatial",
    },
    {
      title: "Data-quality evidence",
      detail: `${evidence.data_quality?.status ?? "Unknown"}; ML ${evidence.data_quality?.ml_eligible ? "eligible" : "ineligible"}.`,
      source: "quality",
    },
  ];
  return (
    <>
      <section className="panel p-4" aria-label="Uploaded anomaly investigation">
        <p className="section-kicker">Uploaded Dataset Analysis</p>
        <h2 className="mt-1 text-lg font-extrabold">
          {anomaly.root_cause_estimate} · {anomaly.timestamp}
        </h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {anomaly.station} · exact uploaded-dataset record (not a persistent alert).
        </p>
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          <DetailStat
            label="Temperature"
            value={
              anomaly.observation["temperature_c"] !== null &&
              anomaly.observation["temperature_c"] !== undefined
                ? `${(anomaly.observation["temperature_c"] as number).toFixed(1)}°C`
                : "Not available"
            }
            emphasis
            tone="bg-anomaly-soft"
          />
          <DetailStat
            label="Humidity"
            value={
              anomaly.observation["relative_humidity_pct"] !== null &&
              anomaly.observation["relative_humidity_pct"] !== undefined
                ? `${(anomaly.observation["relative_humidity_pct"] as number).toFixed(1)}% RH`
                : "Not available"
            }
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label="Pressure"
            value={
              anomaly.observation["pressure_hpa"] !== null &&
              anomaly.observation["pressure_hpa"] !== undefined
                ? `${(anomaly.observation["pressure_hpa"] as number).toFixed(1)} hPa`
                : "Not available"
            }
            tone="bg-surface-blue-tint"
          />
        </div>
        <div className="mt-2.5 divide-y divide-border rounded-xl border border-border px-2.5">
          <FactRow label="Decision" value={anomaly.decision} />
          <FactRow
            label="Score"
            value={
              anomaly.score !== null && anomaly.score !== undefined
                ? anomaly.score.toFixed(2)
                : "Not available"
            }
          />
          <FactRow label="Confidence" value="Not estimated" />
          <FactRow label="Root-cause estimate" value={anomaly.root_cause_estimate} />
        </div>
        <div className="mt-2.5">
          <EvidenceList evidence={items} loading={false} />
        </div>
        <div className="mt-2.5 rounded-xl border border-border p-2.5">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Explanation</p>
          <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
            {anomaly.explanation}
          </p>
        </div>
        {anomaly.correction && (
          <div className="mt-2.5 rounded-xl border border-info/30 bg-info-soft p-2.5">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
              Suggested correction
            </p>
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              Original:{" "}
              <strong className="text-foreground">
                {anomaly.correction.original_value ?? "—"}
              </strong>{" "}
              → Suggested:{" "}
              <strong className="text-foreground">
                {anomaly.correction.suggested_value ?? "—"}
              </strong>
              . {anomaly.correction.reason}
            </p>
          </div>
        )}
        <div className="mt-2.5 rounded-xl border border-border p-2.5">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
            Recommended action
          </p>
          <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
            {anomaly.recommended_action} (Recommendation, not a confirmed diagnosis.)
          </p>
        </div>
        <div className="mt-2.5">
          <Button size="sm" variant="outline" onClick={onBack}>
            <ArrowLeft />
            Back to results
          </Button>
        </div>
      </section>
    </>
  );
}
