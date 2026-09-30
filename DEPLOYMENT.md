# SkyGuard AI — Deployment Guide (Vercel + Render)

Verified on the release-candidate audit (2026-09-30). Frontend is a TanStack
Start app served by Nitro 3; backend is FastAPI serving frozen artifacts.

## A. Frontend on Vercel

The frontend is an **SSR app** (Nitro `node-server` preset locally). Vercel is
supported through Nitro's built-in `vercel` preset — **no `vercel.json` is
needed**; the build emits the standard Vercel Build Output API (`.vercel/output/`),
whose SSR server function also serves client-side routes (direct URL access
works; no SPA rewrites required).

### One-time settings (Vercel dashboard → Project → Settings)

| Setting | Value |
| --- | --- |
| Framework Preset | Other (or Vite) |
| Root Directory | `Frontend` |
| Build Command | `npm run build` |
| Output Directory | *leave default* — Vercel reads `.vercel/output` from the preset build |
| Install Command | `npm install` |

### Environment variables (Production + Preview)

| Variable | Example | Notes |
| --- | --- | --- |
| `NITRO_PRESET` | `vercel` | Selects Nitro's Vercel preset during build |
| `VITE_API_BASE_URL` | `https://skyguard-api.onrender.com` | Public backend origin, **no trailing slash**. The browser uses it for all REST calls and converts it to `wss://…` for the replay WebSocket. |

There are no secrets in the frontend; everything it sends is public API
traffic. Never point `VITE_API_BASE_URL` at a service that is not meant to be
public.

### Local pre-flight (exact commands)

```bash
cd Frontend
npm install
NITRO_PRESET=vercel npm run build     # must exit 0 and create .vercel/output/
```

Deploy with the Vercel CLI (`npx vercel --prod`) or push and let the Git
integration build. Client-side routing works on refresh because the SSR
function serves all routes.

## B. Backend on Render

`Backend/render.yaml` is a ready Render blueprint (Python runtime,
`rootDir: Backend`, health check `/health`).

### Start command (exact)

```bash
python -m src.api.run
```

`src/api/run.py` binds `0.0.0.0`-style hosting correctly on Render:
**`PORT` (injected by Render) takes precedence**, then `SKYGUARD_PORT`, then
the local default `8000`. Host defaults to `127.0.0.1` locally; set
`SKYGUARD_HOST=0.0.0.0` if you start the service without Render's runtime
managing the bind.

### Environment variables (Render dashboard)

| Variable | Value | Notes |
| --- | --- | --- |
| `SKYGUARD_ALLOWED_ORIGINS` | `https://<your-app>.vercel.app` | Comma-separated exact origins. **Never `*`** (credentials are allowed). Defaults to localhost pair for development only. |
| `SKYGUARD_DATA_ROOT` | `/opt/render/project/src` | Directory that contains `data/`, `models/`, `reports/`. |
| `LIVE_SOURCE_MODE` | `DISABLED` | Keep off unless demoing the controlled live stream. |
| `IMD_BASE_URL` | *(empty)* | Only for `LIVE_SOURCE_MODE=LIVE_IMD`. |

`requirements.txt` is pinned and installed automatically by Render's Python
runtime (Python 3.14).

### Frozen artifacts — required manual provisioning step

The API intentionally serves **frozen artifacts** (real GHCNh observations,
frozen ensemble predictions, trained Delhi models). These are *build inputs*,
not source code, and are git-ignored, so a fresh Render checkout cannot boot
without them. `DataStore.load()` fails fast naming any missing file.

Provision once (from this machine, where the artifacts exist):

```bash
# ~400 MB total. Copy the required trees to the Render service disk:
scp -r Backend/data/processed Backend/data/ensemble Backend/data/root_cause \
      Backend/data/noaa/processed Backend/models Backend/data/showcase \
      <render-service>:/opt/render/project/src/data/../   # adjust target layout
# Metadata (station_mapping, neighbor_graph, detectors) IS in git and needs no copy.
```

Then restart the service. Startup validation lists anything still missing, e.g.
`Missing required artifacts: ['data/processed/delhi_clean.csv', ...]`.

Timeline artifacts (`data/showcase/timeline/<STATION>.json`) are optional but
recommended: without them the timeline API still serves real observations and
honestly reports `detector.available = false` instead of inventing events.
Rebuild them any time with:

```bash
cd Backend && .venv/Scripts/python.exe -m src.showcase.build_timeline
```

### First-boot verification

```bash
curl https://<render-host>/health
curl https://<render-host>/api/v1/network/summary   # stations_monitored=14
```

## C. Cross-origin wiring checklist

1. Frontend `VITE_API_BASE_URL=https://<render-host>` (HTTPS; WebSocket becomes `wss://<render-host>/api/v1/live` — supported on Render).
2. Backend `SKYGUARD_ALLOWED_ORIGINS=https://<vercel-host>` (exact scheme+host, no trailing slash).
3. Redeploy the **frontend** after changing `VITE_API_BASE_URL` (Vite bakes env vars at build time).

## D. What was deliberately NOT changed

- No fabricated capability: the UI labels everything `historical_replay` / `CONTROLLED DEMO`; the only "live" surface is the IMD WIS2 integration, which stays `DISABLED` without configured credentials/endpoints.
- No `vercel.json`: the Nitro Vercel preset emits everything Vercel needs; an SPA-style rewrite file would fight the SSR function.
- No dataset/model files added to git: keeps the repo light and preserves the frozen-artifact provenance contract (they are reproducible via the pipeline and documented in `docs/SIH26073_COMPLIANCE_AUDIT.md`).
