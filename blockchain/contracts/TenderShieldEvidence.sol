// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract TenderShieldEvidence {
    struct EvidenceRecord {
        string caseId;
        string tenderId;
        bytes32 evidenceHash;
        bytes32 auditHeadHash;
        bytes32 dossierHash;
        address auditor;
        uint256 recordedAt;
        string auditorAction;
        bool exists;
    }

    mapping(bytes32 => EvidenceRecord) private records;

    event EvidenceCommitted(
        string caseId,
        string tenderId,
        bytes32 evidenceHash,
        bytes32 auditHeadHash,
        bytes32 dossierHash,
        address indexed auditor,
        uint256 recordedAt,
        string auditorAction
    );

    function commitEvidence(
        string calldata caseId,
        string calldata tenderId,
        bytes32 evidenceHash,
        bytes32 auditHeadHash,
        bytes32 dossierHash,
        string calldata auditorAction
    ) external {
        require(bytes(caseId).length > 0, "Case ID required");
        require(evidenceHash != bytes32(0), "Evidence hash required");

        bytes32 key = keccak256(bytes(caseId));
        require(!records[key].exists, "Evidence already committed");

        records[key] = EvidenceRecord({
            caseId: caseId,
            tenderId: tenderId,
            evidenceHash: evidenceHash,
            auditHeadHash: auditHeadHash,
            dossierHash: dossierHash,
            auditor: msg.sender,
            recordedAt: block.timestamp,
            auditorAction: auditorAction,
            exists: true
        });

        emit EvidenceCommitted(
            caseId, tenderId, evidenceHash, auditHeadHash, dossierHash,
            msg.sender, block.timestamp, auditorAction
        );
    }

    function getEvidence(string calldata caseId) external view returns (EvidenceRecord memory) {
        bytes32 key = keccak256(bytes(caseId));
        require(records[key].exists, "Evidence not found");
        return records[key];
    }

    function evidenceExists(string calldata caseId) external view returns (bool) {
        return records[keccak256(bytes(caseId))].exists;
    }
}
