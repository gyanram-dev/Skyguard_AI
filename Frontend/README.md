# SkyGuard AI

Context-aware weather intelligence and AWS sensor-trust platform.

Frontend dashboard for the SkyGuard FastAPI backend. All station, alert,
investigation, probe, replay, and evaluation data comes from the backend
REST/WebSocket API — no mock data, no fabricated results.

## Tech stack

- React 19 + TypeScript
- TanStack Start (SSR) + TanStack Router (file-based routing in `src/routes/`)
- TanStack Query (server state) + local state for the WebSocket replay stream
- Vite 8 + Nitro (build / preview server)
- Tailwind CSS 4 + shadcn-style UI components (`src/components/ui/`)
- Recharts (sensor trend charts)

## Prerequisites

- Node.js (recent LTS) and npm
- A running SkyGuard backend (see the repository root README)

## Install

```sh
npm install
```

## Environment

Copy `.env.example` to `.env`:

```sh
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Either `NEXT_PUBLIC_API_URL` (the deployment variable — set it in the Vercel
project) or `VITE_API_BASE_URL` (kept for local `.env` files and existing
deployments) configures the backend origin; `NEXT_PUBLIC_API_URL` wins when
both are set. The app falls back to `http://localhost:8000` when neither is
set. Vite inlines these at build time, so redeploy after changing them.

## Development

```sh
npm run dev
```

Starts the local dev server (default port 3000, covered by backend CORS).
Open the printed `localhost` URL.

## Production build

```sh
npm run build
```

To preview the production build locally:

```sh
npm run preview
```

## Lint & format

```sh
npm run lint
npx tsc --noEmit
```

(`npm run lint` also covers pre-existing line-ending noise across untouched
scaffold files; the application sources under `src/lib`, `src/components`,
`src/routes`, and `src/hooks` are lint-clean.)

## Notes

- API layer: `src/lib/api.ts` (native fetch, `VITE_API_BASE_URL`,
  centralized errors). Live replay transport: `src/lib/live.ts`.
- Server state: `src/hooks/useSkyguard.ts` (React Query);
  streaming replay state: `src/hooks/useLiveReplay.ts` (local state only).
- Static images (India map, icons) live in `public/assets/` and are served
  from `/assets/*`.
- Data mode is historical replay unless the backend reports otherwise; the
  header and replay bar label it honestly.
