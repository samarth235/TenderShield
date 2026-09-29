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

  it("stores each document version as its own record without overwriting the historical one", async function () {
    const contract = await ethers.deployContract("TenderShieldEvidence");
    await contract.waitForDeployment();
    const v1 = "SNAP-S1:DOC-V001-COMP@v1";
    const v2 = "SNAP-S2:DOC-V001-COMP@v2";
    const h1 = `0x${"a1".repeat(32)}`;
    const h2 = `0x${"c3".repeat(32)}`;
    await (await contract.commitEvidence(v1, "TN-TEST", h1, auditHash, ethers.ZeroHash, "V1_FINALIZED")).wait();
    await (await contract.commitEvidence(v2, "TN-TEST", h2, auditHash, ethers.ZeroHash, "V2_ACCEPTED")).wait();

    expect((await contract.getEvidence(v1)).evidenceHash).to.equal(h1);
    expect((await contract.getEvidence(v1)).auditorAction).to.equal("V1_FINALIZED");
    expect((await contract.getEvidence(v2)).evidenceHash).to.equal(h2);
    try {
      await contract.commitEvidence(v1, "TN-TEST", h2, auditHash, ethers.ZeroHash, "OVERWRITE");
      expect.fail("a historical version record must not be overwritten");
    } catch (error) {
      expect(String(error)).to.include("Evidence already committed");
    }
    expect((await contract.getEvidence(v1)).evidenceHash).to.equal(h1);
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
