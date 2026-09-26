# SkyGuard AI

Context-aware weather intelligence and AWS sensor-trust platform.

Frontend only. Runs standalone with local mock data — no backend required.

## Tech stack

- React 19 + TypeScript
- TanStack Start (SSR) + TanStack Router (file-based routing in `src/routes/`)
- TanStack Query
- Vite 8 + Nitro (build / preview server)
- Tailwind CSS 4 + shadcn-style UI components (`src/components/ui/`)
- Recharts (sensor trend charts)

## Prerequisites

- Node.js (see `.nvmrc` if present, otherwise any recent LTS) and npm

## Install

```sh
npm install
```

## Development

```sh
npm run dev
```

Starts the local dev server. Open the printed `localhost` URL.

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
npm run format
```

## Notes

- The dashboard (`/`) uses centralized mock data defined in `src/routes/index.tsx`
  (stations, alerts, sensor readings, network activity). It is intentional:
  keep the app fully runnable without a backend.
- Static images (India map, robot, icons) live in `public/assets/` and are
  served from `/assets/*`.
- No environment variables are required to run the frontend.
