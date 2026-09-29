import "dotenv/config";
import hardhatEthers from "@nomicfoundation/hardhat-ethers";
import hardhatMocha from "@nomicfoundation/hardhat-mocha";
import { defineConfig } from "hardhat/config";

const privateKey = process.env.DEPLOYER_PRIVATE_KEY;

export default defineConfig({
  plugins: [hardhatEthers, hardhatMocha],
  solidity: "0.8.24",
  networks: {
    mst_testnet: {
      type: "http",
      chainId: 91562037,
      url: process.env.MST_TESTNET_RPC_URL || "https://testnetrpc.mstblockchain.com",
      accounts: privateKey ? [privateKey] : [],
    },
  },
});
