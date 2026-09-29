import { expect } from "chai";
import { network } from "hardhat";

const { ethers } = await network.connect();
const hash = `0x${"11".repeat(32)}`;
const auditHash = `0x${"22".repeat(32)}`;
const dossierHash = `0x${"33".repeat(32)}`;

describe("TenderShieldEvidence", function () {
  it("stores only a signed, timestamped commitment and reads it back", async function () {
    const [auditor] = await ethers.getSigners();
    const contract = await ethers.deployContract("TenderShieldEvidence");
    await contract.waitForDeployment();

    expect(await contract.evidenceExists("SNAP-TEST-001")).to.equal(false);
    await (await contract.commitEvidence("SNAP-TEST-001", "TN-TEST-001", hash, auditHash, dossierHash, "FURTHER_REVIEW")).wait();

    const record = await contract.getEvidence("SNAP-TEST-001");
    expect(record.caseId).to.equal("SNAP-TEST-001");
    expect(record.tenderId).to.equal("TN-TEST-001");
    expect(record.evidenceHash).to.equal(hash);
    expect(record.auditHeadHash).to.equal(auditHash);
    expect(record.dossierHash).to.equal(dossierHash);
    expect(record.auditor).to.equal(auditor.address);
    expect(record.recordedAt).to.be.greaterThan(0n);
    expect(record.auditorAction).to.equal("FURTHER_REVIEW");
    expect(await contract.evidenceExists("SNAP-TEST-001")).to.equal(true);
  });

  it("rejects a second commitment for the same snapshot", async function () {
    const contract = await ethers.deployContract("TenderShieldEvidence");
    await contract.waitForDeployment();
    await (await contract.commitEvidence("SNAP-DUP", "TN-TEST", hash, auditHash, dossierHash, "REVIEW")).wait();
    try {
      await contract.commitEvidence("SNAP-DUP", "TN-TEST", hash, auditHash, dossierHash, "REVIEW");
      expect.fail("duplicate commitment should revert");
    } catch (error) {
      expect(String(error)).to.include("Evidence already committed");
    }
  });
});
