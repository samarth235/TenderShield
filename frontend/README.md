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
| `/` | Landing page with a "Load demonstration tender" button. Once loaded: tender summary, key stats, the 8-stage analysis pipeline with timings, findings and bidders |
| `/rulebook` | Each rule traced from clause to machine rule: clause text and PDF page, AI extraction, deterministic condition, and the result for every bidder |
| `/compliance` | 6 × 18 compliance matrix. Clicking a cell opens a panel with the expected value, actual value, reason and the evidence excerpt with page link |
| `/graph` | Cytoscape relationship graph (vendors, directors, addresses, co-bidding) and a trace of the connection between any two vendors |
| `/intelligence` | Proposal-similarity heatmap, section bars, passages side by side, and a behaviour table with flags and Isolation Forest rank |
| `/findings` | Findings split into investigation signals, compliance and data quality |
| `/findings/:id` | Evidence card. Toggling evidence on/off re-scores the finding live (counterfactual robustness test). Also shows the reasoning chain, robustness report, auditor disposition and audit trail |
| `/integrity` | Finalise and seal the evidence (SHA-256), view the on-chain payload, verify, and the tamper demo |

## Design system

Tokens live in `src/styles/tokens.css`. The look is a "forensic ledger": warm paper canvas, ink-navy chrome, one amber brand accent, and a fixed semantic palette for evidence states (`--high`, `--medium`, `--low`, `--pass`, `--fail`, `--unknown`, `--na`) and evidence families (`--fam-*`). Light and dark themes are both supported; use the toggle in the top bar.

Shared components (`Badge`, `Card`, `StatTile`, `Button`, `Drawer`, `Meter`, `Switch`, `Callout`, and others) are in `src/components/ui.tsx`.
