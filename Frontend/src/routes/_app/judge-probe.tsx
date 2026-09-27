import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/format";
import { useStations } from "@/hooks/useSkyguard";
import { InfoRow, LoadingBlock, SectionCard } from "@/components/shared";

export const Route = createFileRoute("/_app/judge-probe")({
  head: () => ({
    meta: [{ title: "Judge Probe | SkyGuard AI" }],
  }),
  component: JudgeProbePage,
});

/**
 * Frontend-ready probe surface. The backend does not expose a POST analysis
 * endpoint yet, so Analyze never fabricates ML results — it reports the
 * disconnected state and keeps the form structured for later wiring.
 */
function JudgeProbePage() {
  const stationsQuery = useStations();
  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);

  const availableStations = useMemo(
    () => stations.filter((station) => station.data_available),
    [stations],
  );

  const [stationId, setStationId] = useState("");
  const [temperature, setTemperature] = useState("");
  const [pressure, setPressure] = useState("");
  const [humidity, setHumidity] = useState("");
  const [attempted, setAttempted] = useState(false);

  const selectedStation =
    stationId === "" ? null : (stations.find((s) => s.station_id === stationId) ?? null);

  return (
    <>
      <SectionCard
        title="Probe input"
        subtitle="Compose a weather observation to test through SkyGuard."
        action={
          <span className="flex size-8 items-center justify-center rounded-xl bg-info-soft text-info">
            <FlaskConical className="size-4" />
          </span>
        }
      >
        {stationsQuery.isPending && <LoadingBlock label="Loading station list…" />}
        {stationsQuery.isError && (
          <p className="text-[11px] text-muted-foreground" role="alert">
            Station list unavailable: {errorMessage(stationsQuery.error)}
          </p>
        )}
        {!stationsQuery.isPending && !stationsQuery.isError && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block text-[11px] font-bold text-foreground">
              Station
              <select
                value={stationId}
                onChange={(event) => {
                  setStationId(event.target.value);
                  setAttempted(false);
                }}
                className="mt-1 h-9 w-full cursor-pointer rounded-md border border-input bg-card px-2 text-xs font-semibold"
              >
                <option value="">Select a station…</option>
                {availableStations.map((station) => (
                  <option key={station.station_id} value={station.station_id}>
                    {station.station_id} · {station.city}
                  </option>
                ))}
              </select>
            </label>
            <div className="text-[11px] text-muted-foreground sm:self-end">
              {selectedStation ? (
                <p className="pb-2">
                  {selectedStation.city} · last updated{" "}
                  {selectedStation.last_updated ?? "not available"}
                </p>
              ) : (
                <p className="pb-2">Only stations with backend data can be probed.</p>
              )}
            </div>
            {(
              [
                {
                  label: "Temperature (°C)",
                  value: temperature,
                  set: setTemperature,
                  placeholder: "e.g. 32.4",
                },
                {
                  label: "Pressure (hPa)",
                  value: pressure,
                  set: setPressure,
                  placeholder: "e.g. 1008.2",
                },
                {
                  label: "Humidity (% RH)",
                  value: humidity,
                  set: setHumidity,
                  placeholder: "e.g. 68.0",
                },
              ] as const
            ).map((field) => (
              <label key={field.label} className="block text-[11px] font-bold text-foreground">
                {field.label}
                <Input
                  value={field.value}
                  onChange={(event) => {
                    field.set(event.target.value);
                    setAttempted(false);
                  }}
                  placeholder={field.placeholder}
                  inputMode="decimal"
                  className="mt-1 h-9 bg-card text-xs"
                />
              </label>
            ))}
            <div className="flex items-end">
              <Button
                type="button"
                onClick={() => setAttempted(true)}
                disabled={stationId === ""}
                className="w-full sm:w-auto"
              >
                <FlaskConical />
                Analyze observation
              </Button>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Result" subtitle="Probe analysis output">
        {!attempted ? (
          <p className="text-[11px] leading-snug text-muted-foreground">
            No analysis yet. Choose a station, enter an observation, and run the probe.
          </p>
        ) : (
          <div
            className="rounded-xl border border-warning/30 bg-warning-soft px-3 py-2.5"
            role="status"
          >
            <p className="text-[11px] font-extrabold text-warning-deep">
              Probe API not connected yet
            </p>
            <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
              The backend does not expose an analysis endpoint in this phase, so no trust verdict is
              shown. The input above is preserved and ready to wire once the endpoint exists.
            </p>
            <div className="mt-2 border-t border-warning/30 pt-2">
              <InfoRow label="Station" value={stationId} />
              <InfoRow label="Temperature" value={temperature === "" ? "—" : `${temperature} °C`} />
              <InfoRow label="Pressure" value={pressure === "" ? "—" : `${pressure} hPa`} />
              <InfoRow label="Humidity" value={humidity === "" ? "—" : `${humidity} % RH`} />
            </div>
          </div>
        )}
      </SectionCard>
    </>
  );
}
