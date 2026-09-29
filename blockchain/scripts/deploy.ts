import { network } from "hardhat";

const { ethers } = await network.connect();
const activeNetwork = await ethers.provider.getNetwork();
if (activeNetwork.chainId !== 91562037n) {
  throw new Error(`Refusing to deploy outside MST Testnet (got chain ID ${activeNetwork.chainId}).`);
}
const [deployer] = await ethers.getSigners();
if (!deployer) throw new Error("Set DEPLOYER_PRIVATE_KEY in blockchain/.env before deploying.");
if ((await ethers.provider.getBalance(deployer.address)) === 0n) {
  throw new Error(`Deployer ${deployer.address} has no testnet gas. Fund it at https://faucet.mstblockchain.com/`);
}
const contract = await ethers.deployContract("TenderShieldEvidence");
await contract.waitForDeployment();
console.log(`TenderShieldEvidence deployed to: ${await contract.getAddress()}`);
