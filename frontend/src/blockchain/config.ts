// Set this only after deploying TenderShieldEvidence on MST Testnet.
export const TENDERSHIELD_CONTRACT_ADDRESS = import.meta.env.VITE_TENDERSHIELD_CONTRACT_ADDRESS?.trim() ?? "";
export const MST_TESTNET_CHAIN_ID = 91562037n;
export const MST_TESTNET_RPC_URL = "https://testnetrpc.mstblockchain.com";
export const MST_TESTNET_EXPLORER = "https://testnet.mstscan.com";
