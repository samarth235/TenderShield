import { ethers, type Eip1193Provider } from "ethers";

import type { ChainPayload } from "../api/types";
import { TENDERSHIELD_ABI } from "./abi";
import { MST_TESTNET_CHAIN_ID, MST_TESTNET_RPC_URL, TENDERSHIELD_CONTRACT_ADDRESS } from "./config";

type BridgeKeyProvider = Eip1193Provider & { isBridgeKey?: boolean };
type AnnouncedProvider = { info: { name: string; rdns?: string }; provider: BridgeKeyProvider };

declare global {
  interface Window {
    ethereum?: BridgeKeyProvider;
    bridgekey?: BridgeKeyProvider;
  }
}

export type EvidenceRecord = {
  caseId: string;
  tenderId: string;
  evidenceHash: string;
  auditHeadHash: string;
  dossierHash: string;
  auditor: string;
  recordedAt: bigint;
  auditorAction: string;
};

export function contractConfigured(): boolean {
  return ethers.isAddress(TENDERSHIELD_CONTRACT_ADDRESS);
}

export function asBytes32(value: string, field: string): string {
  const hex = value.startsWith("0x") ? value : `0x${value}`;
  if (!/^0x[0-9a-fA-F]{64}$/.test(hex)) throw new Error(`${field} must be a 64-character SHA-256 hex digest.`);
  return hex;
}

function requireContractAddress(): string {
  if (!contractConfigured()) throw new Error("MST Testnet contract address is not configured. Set VITE_TENDERSHIELD_CONTRACT_ADDRESS after deployment.");
  return TENDERSHIELD_CONTRACT_ADDRESS;
}

async function bridgeKeyProvider(): Promise<Eip1193Provider> {
  // EIP-6963 selects BridgeKey when several extensions are installed.
  const announced: AnnouncedProvider[] = [];
  const collect = (event: Event) => announced.push((event as CustomEvent<AnnouncedProvider>).detail);
  window.addEventListener("eip6963:announceProvider", collect);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  await new Promise((resolve) => window.setTimeout(resolve, 150));
  window.removeEventListener("eip6963:announceProvider", collect);
  const bridgeKey = announced.find((entry) =>
    entry.info.rdns === "io.bridgekey.wallet" || entry.provider.isBridgeKey === true || /bridgekey/i.test(entry.info.name),
  );
  if (bridgeKey) return bridgeKey.provider;
  if (window.bridgekey?.isBridgeKey) return window.bridgekey;
  if (window.ethereum?.isBridgeKey) return window.ethereum;
  if (announced.length > 0) throw new Error("BridgeKey was not found among browser wallets. Enable its Chrome extension in this browser, then reload the page.");
  if (window.ethereum) return window.ethereum;
  throw new Error("No EVM wallet provider found. Open this page in Chrome with the BridgeKey extension enabled, or in BridgeKey's Web3 browser. Embedded preview browsers cannot load Chrome extensions.");
}

export async function connectWallet() {
  const provider = new ethers.BrowserProvider(await bridgeKeyProvider());
  await provider.send("eth_requestAccounts", []);
  const network = await provider.getNetwork();
  if (network.chainId !== MST_TESTNET_CHAIN_ID) throw new Error("Switch BridgeKey to MST Testnet (chain ID 91562037).");
  const signer = await provider.getSigner();
  return { address: await signer.getAddress(), provider };
}

export async function getEvidence(caseId: string): Promise<EvidenceRecord | null> {
  const address = requireContractAddress();
  const provider = new ethers.JsonRpcProvider(MST_TESTNET_RPC_URL, Number(MST_TESTNET_CHAIN_ID));
  const contract = new ethers.Contract(address, TENDERSHIELD_ABI, provider);
  if (!(await contract.evidenceExists(caseId))) return null;
  const record = await contract.getEvidence(caseId);
  return {
    caseId: record.caseId,
    tenderId: record.tenderId,
    evidenceHash: record.evidenceHash,
    auditHeadHash: record.auditHeadHash,
    dossierHash: record.dossierHash,
    auditor: record.auditor,
    recordedAt: record.recordedAt,
    auditorAction: record.auditorAction,
  };
}

export async function commitEvidenceToBlockchain(payload: ChainPayload, dossierHash: string, onSubmitted: (hash: string) => void) {
  const address = requireContractAddress();
  const { address: auditor, provider } = await connectWallet();
  const contract = new ethers.Contract(address, TENDERSHIELD_ABI, await provider.getSigner());
  if (await contract.evidenceExists(payload.case_id)) throw new Error(`${payload.case_id} is already committed on MST Testnet; existing records are never overwritten.`);
  const tx = await contract.commitEvidence(
    payload.case_id,
    payload.tender_id,
    asBytes32(payload.evidence_hash, "Evidence hash"),
    asBytes32(payload.audit_head_hash, "Audit head hash"),
    dossierHash ? asBytes32(dossierHash, "Dossier hash") : ethers.ZeroHash,
    payload.auditor_actions.join(",") || "NONE",
  );
  onSubmitted(tx.hash);
  const receipt = await tx.wait();
  if (!receipt || receipt.status !== 1) throw new Error("MST Testnet transaction did not succeed.");
  return { transactionHash: receipt.hash, auditor };
}

export function walletError(error: unknown): string {
  const e = error as { code?: number | string; shortMessage?: string; message?: string };
  if (e?.code === 4001 || e?.code === "ACTION_REJECTED") return "Transaction cancelled by auditor.";
  return e?.shortMessage || e?.message || String(error);
}
