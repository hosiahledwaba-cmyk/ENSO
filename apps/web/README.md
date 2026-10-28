# ENSO Shield Web

React + TypeScript (Vite) frontend. At Milestone 0 it shows real API liveness
(from `GET /health`) and a roadmap of **planned, unimplemented** capabilities.
It displays no forecasts, risk scores or sample data.

## Commands

```powershell
npm install
npm run dev        # http://localhost:5173
npm test           # Vitest + Testing Library (jsdom)
npm run lint       # ESLint
npm run typecheck  # tsc -b (strict)
npm run build      # production bundle in dist/
```

## Configuration

| Variable            | Default                 | Notes                                   |
| ------------------- | ----------------------- | --------------------------------------- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Inlined at build time; must be http(s). |

> TypeScript is pinned to 6.0.x because `typescript-eslint` 8.x does not yet support TypeScript 7.
