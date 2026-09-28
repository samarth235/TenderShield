# TenderShield Nexus — Frontend

React + TypeScript investigation dashboard for the TenderShield Nexus backend. It is built with Vite and uses TanStack Query for data, Cytoscape for the relationship graph, and IBM Plex type.

## Run

```bash
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api` to `http://localhost:8000`, so start the backend first (`make run` from the repo root). To point at another backend, set `VITE_API_TARGET` for the dev proxy or `VITE_API_BASE` for a built bundle.

```bash
npm run build        # type-check + production bundle in dist/
npm run typecheck
```

## Screens

| Route | Purpose |
|---|---|
| `/` | Landing page with a "Load demonstration tender" button. Once loaded: tender summary, key stats, findings and bidders |
| `/compliance` | Rules & compliance: 6 × 18 compliance matrix. Clicking a requirement shows its source clause, the AI extraction and the deterministic check, with the result for every bidder. Clicking a cell opens the expected value, actual value, reason and evidence excerpt with page link. `/rulebook` redirects here |
| `/graph` | Cytoscape relationship graph (vendors, directors, addresses, co-bidding) and a trace of the connection between any two vendors |
| `/intelligence` | Bidder pairs ranked by proposal similarity against the tender median, section bars for the selected pair, and all matching passages side by side in an expandable list |
| `/findings` | Findings split into investigation signals, compliance and data quality |
| `/findings/:id` | Evidence card. Toggling evidence on/off re-scores the finding live (counterfactual robustness test). Also shows the auditor disposition, source documents, audit trail, reasoning chain and robustness report |
| `/integrity` | Finalise and seal the evidence (SHA-256), view the on-chain payload, verify, and the tamper demo |

## Design system

Tokens live in `src/styles/tokens.css`. The look is a "forensic ledger": neutral canvas, black text, a light sidebar, a deep navy brand colour, and a fixed semantic palette for evidence states (`--high`, `--medium`, `--low`, `--pass`, `--fail`, `--unknown`, `--na`) and evidence families (`--fam-*`). Light and dark themes are both supported; use the toggle in the top bar.

Shared components (`Badge`, `Card`, `StatTile`, `Button`, `Drawer`, `Meter`, `Switch`, `Callout`, and others) are in `src/components/ui.tsx`.
