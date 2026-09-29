# MST Testnet evidence commitments

This package anchors TenderShield's existing SHA-256 evidence snapshot and audit-chain head on MST Testnet. Documents, the evidence bundle, bidder data, and the dossier stay off-chain. The contract records the submitting wallet with `msg.sender` and the recording time with `block.timestamp`.

## Build and test

Use Node.js 22 or newer. From `blockchain/`:

```bash
pnpm install
pnpm run compile
pnpm test
```

The frontend ABI in `frontend/src/blockchain/TenderShieldEvidence.json` was extracted from the compiled contract artifact. If the contract interface changes, regenerate that ABI from `artifacts/contracts/TenderShieldEvidence.sol/TenderShieldEvidence.json`.

## Deploy to MST Testnet

Current deployment: [`0xC5a5Eae08f4c33A720073AF5379667cb662d8D80`](https://testnet.mstscan.com/address/0xC5a5Eae08f4c33A720073AF5379667cb662d8D80) on chain ID `91562037`. The frontend's `.env.example` contains this public address.

The demo snapshot `SNAP-22AEB53102EF` was committed by BridgeKey in [transaction `0x7e2924…81a99`](https://testnet.mstscan.com/tx/0x7e2924578cd6f3191c525ed7ac0f43c887a8bda3b0409961f9fb80eaad581a99). Its on-chain evidence hash matches the backend snapshot hash.

1. Copy `.env.example` to `.env` and add a dedicated **testnet-only** deployer private key. Never use a recovery phrase. `.env` is ignored by Git.
2. Fund that deployer address from the [MST Testnet faucet](https://faucet.mstblockchain.com/).
3. Run `pnpm run deploy:mst` and check the transaction/contract in the [MST Testnet explorer](https://testnet.mstscan.com/).
4. Copy the printed contract address into `frontend/.env.local` as `VITE_TENDERSHIELD_CONTRACT_ADDRESS=0x...`, then restart Vite or rebuild the frontend.

The configured RPC is `https://testnetrpc.mstblockchain.com`, chain ID `91562037`. Confirm network settings with MST before a deployment. The frontend reads the contract from the public RPC; signing requires BridgeKey to expose an EIP-1193 provider to the page. A BridgeKey extension is selected through EIP-6963 where available, or the page can be opened in BridgeKey's Web3 browser.

## Integrity flow

1. Finalise a snapshot through the existing backend endpoint.
2. Connect BridgeKey on `/integrity`, then commit the backend's `chain_payload`. The existing `bundle_hash` is sent directly as `evidenceHash`; no second hash is created.
3. Verify on `/integrity`. The page reads `getEvidence(snapshot_id)` and the backend's current evidence hash, then compares them. A backend-only hash check is labelled separately when no blockchain record exists.

The dossier hash is optional because this repository currently exposes dossier **JSON**, not a generated PDF. Leave the field empty to commit `bytes32(0)`; enter a real PDF SHA-256 only if one has been generated and hashed separately. The frontend does not hash the JSON and present it as a PDF digest.

The contract permits one commitment per snapshot ID. A later finalisation creates a new snapshot ID and can be committed separately.

## Browser and demo troubleshooting

- Use a normal Chrome tab with the [BridgeKey extension](https://chromewebstore.google.com/detail/bridgekey/bfjojdcfenehemjgjlepdjomkpginlkg) enabled, or BridgeKey's own Web3 browser. Codex's embedded preview cannot load Chrome extensions, so it will show “No EVM wallet provider found.”
- Unlock BridgeKey and select MST Testnet (RPC `https://testnetrpc.mstblockchain.com`, chain ID `91562037`, currency `tMSTC`, explorer `https://testnet.mstscan.com`). Fund the auditor wallet from the faucet if it needs gas. The deployer and auditor wallets are separate.
- If the contract notice remains after deployment, check `frontend/.env.local` and restart the Vite server. Vite reads environment variables at startup.
- For the tamper demonstration, use **Modify document → Verify integrity → Restore → Verify integrity**. This repository's restore endpoint is `POST /api/demo/restore` (the separate fix guide's `/api/demo/reset` path is incorrect).
