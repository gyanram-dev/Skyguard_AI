import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { FlaskConical, PlugZap } from "lucide-react";

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
import { EmptyState, ErrorState, LoadingState, StatusBadge } from "@/components/common";
import { normalizeStatus } from "@/lib/api";
import { errorMessage, formatTemp } from "@/lib/format";
import { useStations } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/judge-probe")({
  head: () => ({
    meta: [{ title: "Judge Probe | SkyGuard AI" }],
  }),
  component: JudgeProbePage,
});

function toNumberInput(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

/**
 * Interactive demonstration surface. The backend currently exposes no POST
 * probe endpoint, so Analyze honestly reports "not connected" instead of
 * fabricating ML results. Inputs are prefilled from real station readings.
 */
function JudgeProbePage() {
  const stationsQuery = useStations();
  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);
  const availableStations = useMemo(
    () => stations.filter((station) => station.data_available),
    [stations],
  );

  const [stationId, setStationId] = useState<string>("");
  const [temperature, setTemperature] = useState("");
  const [humidity, setHumidity] = useState("");
  const [pressure, setPressure] = useState("");
  const [attempted, setAttempted] = useState(false);

  const selected = useMemo(
    () => availableStations.find((station) => station.station_id === stationId),
    [availableStations, stationId],
  );

  useEffect(() => {
    if (stationId === "" && availableStations.length > 0) {
      const first = availableStations[0];
      if (first) {
        setStationId(first.station_id);
        setTemperature(toNumberInput(first.temperature));
        setHumidity(toNumberInput(first.humidity));
        setPressure(toNumberInput(first.pressure));
      }
    }
  }, [availableStations, stationId]);

  const pickStation = (id: string) => {
    setStationId(id);
    setAttempted(false);
    const row = availableStations.find((station) => station.station_id === id);
    if (row) {
      setTemperature(toNumberInput(row.temperature));
      setHumidity(toNumberInput(row.humidity));
      setPressure(toNumberInput(row.pressure));
    }
  };

  return (
    <>
      {stationsQuery.isPending && <LoadingState message="Loading stations for the probe…" />}
      {stationsQuery.isError && (
        <ErrorState
          message={errorMessage(stationsQuery.error)}
          onRetry={() => stationsQuery.refetch()}
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && availableStations.length === 0 && (
        <EmptyState
          title="No stations available"
          message="The API returned no stations with data to probe."
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && availableStations.length > 0 && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section className="panel p-4" aria-label="Probe input">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="section-kicker">Observation under test</p>
                <h2 className="mt-1 text-lg font-extrabold">Probe Input</h2>
              </div>
              {selected && (
                <StatusBadge status={normalizeStatus(selected.status, selected.data_available)} />
              )}
            </div>

            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="probe-station">Station</Label>
                <Select value={stationId} onValueChange={pickStation}>
                  <SelectTrigger id="probe-station" aria-label="Station">
                    <SelectValue placeholder="Select station" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableStations.map((station) => (
                      <SelectItem key={station.station_id} value={station.station_id}>
                        {station.station_id} · {station.city} · {formatTemp(station.temperature)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="probe-temp">Temperature (°C)</Label>
                  <Input
                    id="probe-temp"
                    inputMode="decimal"
                    value={temperature}
                    onChange={(event) => {
                      setTemperature(event.target.value);
                      setAttempted(false);
                    }}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="probe-humidity">Humidity (% RH)</Label>
                  <Input
                    id="probe-humidity"
                    inputMode="decimal"
                    value={humidity}
                    onChange={(event) => {
                      setHumidity(event.target.value);
                      setAttempted(false);
                    }}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="probe-pressure">Pressure (hPa)</Label>
                  <Input
                    id="probe-pressure"
                    inputMode="decimal"
                    value={pressure}
                    onChange={(event) => {
                      setPressure(event.target.value);
                      setAttempted(false);
                    }}
                  />
                </div>
              </div>

              <Button size="sm" onClick={() => setAttempted(true)}>
                <FlaskConical />
                Analyze observation
              </Button>
              <p className="text-[10px] text-muted-foreground">
                Inputs are prefilled from the selected station&apos;s latest replayed reading and
                remain editable for demonstration.
              </p>
            </div>
          </section>

          <section className="panel p-4" aria-label="Probe result" aria-live="polite">
            <p className="section-kicker">Result</p>
            <h2 className="mt-1 text-lg font-extrabold">Analysis</h2>
            {!attempted ? (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Configure an observation and run the analysis. Results will appear here once the
                probe API is connected.
              </p>
            ) : (
              <div className="mt-3 rounded-xl border border-warning/30 bg-warning-soft p-3">
                <p className="flex items-center gap-2 text-[11px] font-extrabold text-warning-deep">
                  <PlugZap className="size-4" />
                  Probe API not connected yet
                </p>
                <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                  The backend does not expose a probe endpoint in this phase, so no analysis was
                  performed and no ML results are shown. This surface is ready to be wired to a
                  future POST endpoint.
                </p>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
