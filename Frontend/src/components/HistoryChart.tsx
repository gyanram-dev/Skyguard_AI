import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";

/**
 * Reusable single-series history chart in the SkyGuard visual language.
 * Missing values are preserved as gaps (connectNulls is false); the backend
 * never gets an interpolated line drawn through them.
 */
export function HistoryChart({
  data,
  heightClass = "h-[72px]",
  color = "var(--chart-alert)",
}: {
  data: Array<{ time: string; recorded: number | null }>;
  heightClass?: string;
  color?: string;
}) {
  if (data.length === 0) {
    return (
      <p className="flex h-full min-h-[72px] items-center justify-center text-[9px] text-muted-foreground">
        No history available.
      </p>
    );
  }
  return (
    <div className={heightClass}>
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
            stroke={color}
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
