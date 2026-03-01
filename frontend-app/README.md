# Smart Medirag Frontend

React + Vite + Tailwind frontend for Smart Medirag.

## Prerequisites

- Node.js 18+
- npm 9+
- Backend API running at `http://localhost:5000`

## Run locally

```bash
cd frontend-app
npm install
npm run dev
```

Dev server runs at `http://localhost:5173`.

## Build for production

```bash
cd frontend-app
npm run build
npm run preview
```

## Admin routes

- Admin login: `/#/admin/login`
- Admin ingestion console: `/#/admin/ingest`

## UI updates (March 1, 2026)

- Indexed Documents panel now uses responsive fixed heights to avoid overflow/collapse across screen sizes.
- Improved scroll container sizing with `min-h-0` so the document table stays stable in flex layouts.
- Added smoother transitions for panel state changes and verification-result reveal.
- Improved table sizing for the `Doc ID` column and cleaned date-cell alignment.
