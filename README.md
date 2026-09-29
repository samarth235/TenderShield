# 🛡️ TenderShield Nexus

### Explainable Tender Assurance & Evidence Intelligence Platform

> **AI finds the signals. Rules verify the facts. Blockchain protects the evidence. Humans make the final decision.**

TenderShield Nexus is an intelligent procurement assurance platform designed to help investigators and auditors identify suspicious patterns in government tender data.

The platform transforms tender records into **explainable, evidence-backed investigation cases** by combining AI/ML analysis, rule-based compliance checks, entity resolution, document similarity, network analysis, and tamper-evident audit records.

---

## 🚨 The Problem

Government procurement involves large amounts of financial data, multiple bidders, complex tender documents, and extensive compliance requirements.

Traditional auditing is often:

* Manual and time-consuming
* Difficult to scale across large numbers of tenders
* Dependent on disconnected documents and records
* Reactive rather than investigative
* Difficult to trace from an initial anomaly to supporting evidence

A suspicious tender may involve several seemingly unrelated signals:

* Similar bidder identities
* Repeated participation patterns
* Unusual bid values
* Suspicious document similarities
* Connections between companies
* Missing or inconsistent compliance requirements
* Patterns that become visible only when multiple tenders are analyzed together

**TenderShield brings these signals together into a single investigation workflow.**

---

## 💡 Our Solution

TenderShield acts as an **assurance and intelligence layer** over procurement data.

Instead of simply producing a fraud score, the system attempts to answer:

> **"Why is this tender suspicious, what evidence supports the finding, and how are the entities involved connected?"**

The platform follows a layered approach:

```text
                    TENDER DATA
                         │
                         ▼
              ┌─────────────────────┐
              │  Document / Data    │
              │      Analysis       │
              └──────────┬──────────┘
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
        AI / ML       Rules       Entity
        Analysis    Compliance   Resolution
             │           │           │
             └───────────┼───────────┘
                         ▼
                Investigation Case
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
        Evidence      Network      Reasoning
         Analysis      Graph       Engine
             │           │           │
             └───────────┼───────────┘
                         ▼
                Audit / Evidence
                     Record
```

---

# ✨ Key Features

## 🔎 1. Explainable Investigation

TenderShield is designed to go beyond a simple "fraud detected" result.

The system provides supporting signals and evidence so an investigator can understand **why a tender was flagged**.

---

## 🤖 2. AI-Assisted Rule Extraction

Tender documents can contain important requirements hidden inside large amounts of text.

TenderShield extracts relevant procurement rules using:

* Pattern-based extraction
* AI-assisted extraction
* Structured rule representation

This allows tender requirements to be processed by the compliance engine.

---

## ⚖️ 3. Compliance Analysis

The compliance engine checks tender information against extracted and predefined rules.

Instead of relying exclusively on an AI model, objective conditions are verified using deterministic rules wherever possible.

This creates a separation between:

```text
AI → Finds / interprets signals

Rules → Verify objective conditions
```

---

## 🧠 4. Anomaly Detection

TenderShield uses machine-learning techniques to identify unusual procurement patterns.

The backend includes an **Isolation Forest** based anomaly-detection component for identifying records that differ significantly from expected patterns.

This can help surface tenders that deserve additional investigation.

---

## 🏢 5. Entity Resolution

Different records may refer to the same organization or entity using slightly different information.

TenderShield includes entity-resolution capabilities to connect related records and improve investigation accuracy.

This helps investigators move from:

```text
Bidder A
Bidder A Pvt Ltd
A Private Limited
```

toward a common underlying entity where appropriate.

---

## 🕸️ 6. Relationship & Network Analysis

Procurement investigations often require understanding relationships between entities.

TenderShield uses **NetworkX** to construct relationship graphs that can expose connections between:

* Bidders
* Organizations
* Tenders
* Related entities
* Participation patterns

This converts isolated records into an interconnected investigation graph.

---

## 📄 7. Document Similarity

TenderShield analyzes similarities between procurement documents.

This can help surface potentially related documents or repeated content that deserves investigation.

The system supports document-similarity analysis as part of the broader evidence pipeline.

---

## 🔐 8. Evidence Integrity

Investigation evidence needs to remain traceable and tamper-evident.

TenderShield includes an **audit-chain mechanism** for maintaining the integrity of investigation records.

The architecture is designed so that blockchain can provide an additional integrity layer for finalized evidence.

> The current repository contains the audit/evidence architecture; the dedicated Solidity + Hardhat blockchain layer is planned for a future implementation stage.

---

## 🧩 9. Evidence Bundles

Instead of presenting isolated AI outputs, TenderShield organizes relevant findings into evidence-backed investigation cases.

An investigation can therefore progress from:

```text
Signal
  ↓
Finding
  ↓
Supporting Evidence
  ↓
Related Entities
  ↓
Investigation Case
```

---

## 🔄 10. Counterfactual Reasoning

TenderShield includes reasoning and counterfactual components intended to help investigators understand suspicious findings from another perspective.

The goal is not simply:

> "This looks anomalous."

but rather:

> "What underlying conditions contributed to this finding, and what would change the result?"

---

# 🏗️ System Architecture

```text
┌───────────────────────────────────────────────────────┐
│                    TenderShield                       │
└─────────────────────────┬─────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────┐
│                  React Dashboard                      │
│               TypeScript + Vite                       │
│        TanStack Query + Cytoscape.js                  │
└─────────────────────────┬─────────────────────────────┘
                          │ REST API
                          ▼
┌───────────────────────────────────────────────────────┐
│                  FastAPI Backend                       │
├───────────────────────────────────────────────────────┤
│                                                       │
│  Rule Extraction        Compliance Engine             │
│  Entity Resolution      Document Similarity           │
│  Anomaly Detection      Network Analysis              │
│  Reasoning Engine       Counterfactual Analysis       │
│  Audit Chain            Evidence Bundles              │
│                                                       │
└─────────────────────────┬─────────────────────────────┘
                          │
                          ▼
                ┌───────────────────┐
                │ Investigation Case│
                └─────────┬─────────┘
                          │
                          ▼
                ┌───────────────────┐
                │ Evidence / Audit  │
                │     Integrity     │
                └───────────────────┘
                          │
                          ▼
                ┌───────────────────┐
                │ Blockchain Layer  │
                │    (Roadmap)      │
                └───────────────────┘
```

---

# 🖥️ Investigation Workflow

TenderShield is organized around an investigation workflow rather than a simple dashboard.

A typical investigation follows:

```text
01 → Load Tender
      ↓
02 → Extract & Understand Rules
      ↓
03 → Run Compliance Checks
      ↓
04 → Detect Anomalies
      ↓
05 → Resolve Related Entities
      ↓
06 → Explore Relationship Graph
      ↓
07 → Examine Evidence
      ↓
08 → Generate Investigation Case
```

The frontend provides an investigation dashboard for navigating these stages.

---

# 🛠️ Technology Stack

### Frontend

| Technology     | Purpose                             |
| -------------- | ----------------------------------- |
| React          | User interface                      |
| TypeScript     | Type-safe frontend development      |
| Vite           | Frontend build tooling              |
| TanStack Query | API/server-state management         |
| Cytoscape.js   | Investigation/network visualization |

### Backend

| Technology        | Purpose                        |
| ----------------- | ------------------------------ |
| Python            | Backend & analysis             |
| FastAPI           | REST API                       |
| NetworkX          | Relationship/network analysis  |
| Isolation Forest  | Anomaly detection              |
| AI/LLM components | Rule extraction & reasoning    |
| Document analysis | Evidence & similarity analysis |

### Integrity & Future Blockchain

| Technology                     | Purpose                                    |
| ------------------------------ | ------------------------------------------ |
| Audit Chain                    | Tamper-evident investigation records       |
| SHA-based integrity mechanisms | Evidence verification                      |
| Solidity                       | Planned blockchain smart contracts         |
| Hardhat                        | Planned blockchain development environment |

---

# 📁 Project Structure

```text
TenderShield/
│
├── backend/
│   ├── AI / ML components
│   ├── compliance engine
│   ├── rule extraction
│   ├── entity resolution
│   ├── network analysis
│   ├── document similarity
│   ├── reasoning
│   ├── counterfactual analysis
│   ├── audit chain
│   └── evidence bundles
│
├── frontend/
│   ├── React + TypeScript application
│   ├── investigation dashboard
│   ├── visualizations
│   └── API integration
│
├── docs/
│   ├── API documentation
│   ├── pipeline documentation
│   ├── design notes
│   └── OpenAPI schema
│
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       └── frontend-ci.yml
│
├── Makefile
└── README.md
```

---
