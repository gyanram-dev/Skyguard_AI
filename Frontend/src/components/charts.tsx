import {
  Area,
  AreaChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDateTime, formatTime } from "@/lib/format";

export type ChartPoint = {
  time: string;
  recorded: number | null;
};

/** Single recorded-values line; nulls stay gaps (no interpolation). */
export function HistoryChart({
  data,
  height = 120,
  ariaLabel,
}: {
  data: ChartPoint[];
  height?: number;
  ariaLabel: string;
}) {
  if (data.length === 0) {
    return (
      <p
        className="flex items-center justify-center text-[10px] text-muted-foreground"
        style={{ height }}
        role="status"
      >
        No history available.
      </p>
    );
  }
  return (
    <div style={{ height }} aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 3, bottom: 0, left: 3 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 7, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
          <Line
            type="monotone"
            dataKey="recorded"
            stroke="var(--chart-alert)"
            dot={false}
            strokeWidth={2.5}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Compact sparkline for sensor summary cards; nulls stay gaps. */
export function SensorSpark({
  values,
  color,
  gradientId,
}: {
  values: Array<{ index: number; value: number | null }>;
  color: string;
  gradientId: string;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={values}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2.2}
          fill={`url(#${gradientId})`}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export type ReplayTemperaturePoint = {
  time: string;
  temperature: number | null;
  anomaly: boolean;
};

/**
 * Temperature across the replayed observations. Real streamed values only:
 * missing readings stay gaps (no interpolation) and anomaly observations keep
 * a distinct point while the line itself stays neutral, so red is reserved
 * for actual detections.
 */
export function ReplayTemperatureChart({
  data,
  height = 150,
  ariaLabel,
}: {
  data: ReplayTemperaturePoint[];
  height?: number;
  ariaLabel: string;
}) {
  return (
    <div style={{ height }} aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 8, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            domain={["dataMin - 2", "dataMax + 2"]}
            tick={{ fontSize: 8, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
            width={38}
            tickFormatter={(value: number) => value.toFixed(0)}
          />
          <Line
            type="monotone"
            dataKey="temperature"
            stroke="var(--chart-context)"
            strokeWidth={2.2}
            connectNulls={false}
            isAnimationActive={false}
            dot={(props: {
              key?: string | number;
              cx?: number;
              cy?: number;
              payload?: ReplayTemperaturePoint;
            }) => {
              const { key, cx, cy, payload } = props;
              if (payload?.temperature == null || cx === undefined || cy === undefined) {
                return <g key={key} />;
              }
              if (payload.anomaly) {
                return (
                  <circle
                    key={key}
                    cx={cx}
                    cy={cy}
                    r={3.8}
                    fill="var(--anomaly)"
                    stroke="var(--card)"
                    strokeWidth={1.2}
                  />
                );
              }
              return <circle key={key} cx={cx} cy={cy} r={1.5} fill="var(--chart-context)" />;
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Station forensic timeline: the station's full recorded period as three
// stacked measurement strips (temperature / relative humidity / pressure)
// with detector-event markers. Every value is a real recorded observation
// (missing readings stay gaps: connectNulls is off, no smoothing) and every
// marker is an event the backend detector already produced.
// ---------------------------------------------------------------------------

export type ForensicsVariable = "temperature" | "humidity" | "pressure";

export type ForensicsSeries = {
  timestamps: string[];
  temperature: Array<number | null>;
  humidity: Array<number | null>;
  pressure: Array<number | null>;
};

export type ForensicsEvent = {
  timestamp: string;
  variable: string | null;
  severity: string | null;
  pattern: string | null;
  /** Recorded value of each channel at the event timestamp. */
  temperature?: number | null;
  humidity?: number | null;
  pressure?: number | null;
};

/** Per-variable hues, tuned for the dark forensic surface. */
export const VARIABLE_COLORS: Record<ForensicsVariable, string> = {
  temperature: "#F2994A",
  humidity: "#4CB3F0",
  pressure: "#3DD6A8",
};

const STRIP_META: Array<{ key: ForensicsVariable; label: string; unit: string }> = [
  { key: "temperature", label: "Temperature", unit: "\u00b0C" },
  { key: "humidity", label: "Relative\nHumidity", unit: "%" },
  { key: "pressure", label: "Pressure", unit: "hPa" },
];

/** Severity band -> colour. Presentation only; bands come from the backend. */
export function severityColor(severity: string | null | undefined): string {
  switch ((severity ?? "").toUpperCase()) {
    case "CRITICAL":
      return "#FF5C5C";
    case "HIGH":
      return "var(--anomaly)";
    case "MEDIUM":
      return "var(--warning)";
    case "LOW":
      return "var(--sky)";
    default:
      return "var(--muted-foreground)";
  }
}

function axisPeriod(value: number): string {
  const date = new Date(value);
  return date.toLocaleString("en-GB", { month: "short", year: "numeric" });
}

function epochOf(timestamp: string): number {
  const direct = Date.parse(timestamp.replace(" ", "T"));
  return Number.isNaN(direct) ? 0 : direct;
}

function variableOf(event: ForensicsEvent): ForensicsVariable {
  const name = (event.variable ?? "").toLowerCase();
  if (name.startsWith("pressure") || name === "pres") return "pressure";
  if (name.startsWith("hum") || name === "rh" || name === "relative_humidity") {
    return "humidity";
  }
  return "temperature";
}

/**
 * Full-period multi-strip timeline. Strips share one time domain so events
 * line up vertically across temperature, humidity and pressure; the selected
 * variable is drawn at full emphasis while the others stay dimmed.
 */
export function StationForensicsChart({
  series,
  events,
  primary,
  selectedTimestamp,
  onSelectMarker,
  ariaLabel,
}: {
  series: ForensicsSeries;
  events: ForensicsEvent[];
  primary: ForensicsVariable;
  selectedTimestamp?: string | null;
  onSelectMarker?: (timestamp: string) => void;
  ariaLabel: string;
}) {
  const times = series.timestamps.map(epochOf);
  if (times.length === 0) {
    return (
      <p className="py-10 text-center text-[12px] text-muted-foreground" role="status">
        No observations available for this station.
      </p>
    );
  }
  const xDomain: [number, number] = [times[0] ?? 0, times[times.length - 1] ?? 1];
  // Markers carry their own time and their own recorded value, so they never
  // depend on how the series was sampled for display.
  const markers = events
    .map((event) => {
      const variable = variableOf(event);
      const value =
        variable === "humidity"
          ? (event.humidity ?? null)
          : variable === "pressure"
            ? (event.pressure ?? null)
            : (event.temperature ?? null);
      return { ...event, t: epochOf(event.timestamp), variable, value };
    })
    .filter((marker) => marker.value !== null);

  // Callouts: only a few labelled events, spaced apart along the time axis so
  // labels never overlap the way a dense marker cloud would. The strongest
  // severities win; the selected event is always labelled.
  const span = Math.max(1, xDomain[1] - xDomain[0]);
  const minGap = span / 9;
  const ranked = [...markers].sort((a, b) => rank(b.severity) - rank(a.severity));
  const accepted: number[] = [];
  const labelled = new Set<string>();
  for (const marker of ranked) {
    if (labelled.size >= 6) break;
    if (accepted.some((kept) => Math.abs(kept - marker.t) < minGap)) continue;
    accepted.push(marker.t);
    labelled.add(`${marker.timestamp}|${marker.variable}`);
  }
  if (selectedTimestamp) {
    const hit = markers.find((marker) => marker.timestamp === selectedTimestamp);
    if (hit) labelled.add(`${hit.timestamp}|${hit.variable}`);
  }

  return (
    <div className="space-y-0.5" aria-label={ariaLabel}>
      {STRIP_META.map((strip, stripIndex) => {
        const isPrimary = strip.key === primary;
        const color = VARIABLE_COLORS[strip.key];
        const points = times.map((t, index) => ({
          t,
          value: series[strip.key]?.[index] ?? null,
          timestamp: series.timestamps[index],
        }));
        const stripMarkers = markers.filter((marker) => marker.variable === strip.key);
        const stripLabels = stripMarkers.filter((marker) =>
          labelled.has(`${marker.timestamp}|${marker.variable}`),
        );
        const isLast = stripIndex === STRIP_META.length - 1;
        const selectedPoint = selectedTimestamp
          ? points.find((point) => point.timestamp === selectedTimestamp)
          : undefined;
        return (
          <div key={strip.key} className="flex items-start gap-2">
            <div className="w-[92px] shrink-0 pt-1 text-right">
              <p
                className="whitespace-pre-line text-[11px] font-semibold leading-tight"
                style={{ color: isPrimary ? color : "var(--muted-foreground)" }}
              >
                {strip.label}
              </p>
              <p className="text-[10px] text-muted-foreground">({strip.unit})</p>
            </div>
            <div className="min-w-0 flex-1" style={{ height: isLast ? 132 : 108 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={points} margin={{ top: 14, right: 10, bottom: 0, left: 0 }}>
                  <CartesianGrid
                    stroke="var(--chart-grid)"
                    strokeDasharray="2 4"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="t"
                    type="number"
                    scale="time"
                    domain={xDomain}
                    hide={!isLast}
                    tickFormatter={axisPeriod}
                    tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={48}
                  />
                  <YAxis
                    domain={["dataMin - 3", "dataMax + 3"]}
                    tickCount={4}
                    tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
                    axisLine={false}
                    tickLine={false}
                    width={44}
                    tickFormatter={(value: number) => value.toFixed(0)}
                  />
                  <Tooltip
                    contentStyle={{
                      fontSize: 11,
                      borderRadius: 8,
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      color: "var(--card-foreground)",
                    }}
                    labelFormatter={(_label, payload) => {
                      const stamp = (payload?.[0]?.payload as { timestamp?: string } | undefined)
                        ?.timestamp;
                      return stamp ? `${formatDateTime(stamp)} \u00b7 ${strip.unit}` : strip.unit;
                    }}
                  />
                  {selectedPoint && (
                    <ReferenceLine
                      x={selectedPoint.t}
                      stroke={color}
                      strokeOpacity={0.55}
                      strokeDasharray="2 3"
                    />
                  )}
                  <Line
                    type="linear"
                    dataKey="value"
                    stroke={color}
                    strokeWidth={isPrimary ? 1.8 : 1.2}
                    strokeOpacity={isPrimary ? 1 : 0.45}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                    name={strip.label.replace("\n", " ")}
                  />
                  {stripMarkers.length > 0 && (
                    <Scatter
                      data={stripMarkers}
                      dataKey="value"
                      isAnimationActive={false}
                      name="detector event"
                      shape={(props: {
                        cx?: number;
                        cy?: number;
                        payload?: { timestamp?: string; severity?: string | null };
                      }) => {
                        const { cx, cy, payload } = props;
                        if (cx === undefined || cy === undefined) return <g />;
                        const selected = payload?.timestamp === selectedTimestamp;
                        return (
                          <circle
                            cx={cx}
                            cy={cy}
                            r={selected ? 5.5 : 3.4}
                            fill={severityColor(payload?.severity)}
                            stroke={selected ? "#FFFFFF" : "var(--background)"}
                            strokeWidth={selected ? 1.6 : 1}
                          />
                        );
                      }}
                      onClick={(point: unknown) => {
                        if (!onSelectMarker) return;
                        const entry = point as {
                          timestamp?: string;
                          payload?: { timestamp?: string };
                        };
                        const stamp = entry?.timestamp ?? entry?.payload?.timestamp;
                        if (typeof stamp === "string") onSelectMarker(stamp);
                      }}
                    />
                  )}
                  {stripLabels.length > 0 && (
                    <Scatter
                      data={stripLabels}
                      dataKey="value"
                      isAnimationActive={false}
                      legendType="none"
                      tooltipType="none"
                      shape={(props: {
                        cx?: number;
                        cy?: number;
                        payload?: { pattern?: string | null; severity?: string | null };
                      }) => {
                        const { cx, cy, payload } = props;
                        if (cx === undefined || cy === undefined) return <g />;
                        const text = (payload?.pattern ?? "EVENT").toUpperCase();
                        return (
                          <g pointerEvents="none">
                            <line
                              x1={cx}
                              y1={cy - 3}
                              x2={cx}
                              y2={cy - 12}
                              stroke={severityColor(payload?.severity)}
                              strokeOpacity={0.5}
                              strokeWidth={1}
                            />
                            <text
                              x={cx}
                              y={cy - 15}
                              textAnchor="middle"
                              fontSize={9}
                              fontWeight={700}
                              letterSpacing={0.4}
                              fill={severityColor(payload?.severity)}
                              stroke="var(--background)"
                              strokeWidth={2.5}
                              paintOrder="stroke"
                            >
                              {text}
                            </text>
                          </g>
                        );
                      }}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function rank(severity: string | null | undefined): number {
  switch ((severity ?? "").toUpperCase()) {
    case "CRITICAL":
      return 4;
    case "HIGH":
      return 3;
    case "MEDIUM":
      return 2;
    case "LOW":
      return 1;
    default:
      return 0;
  }
}

/** Convert history points (detail series or /history points) to chart points. */
export function toChartPoints(
  series: Array<{ timestamp: string } & { [key: string]: number | string | null | undefined }>,
  variable: string,
): ChartPoint[] {
  return series.map((point) => {
    const raw = point[variable];
    return {
      time: formatTime(point.timestamp),
      recorded: typeof raw === "number" ? raw : null,
    };
  });
}
