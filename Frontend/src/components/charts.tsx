import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import { formatTime } from "@/lib/format";

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
