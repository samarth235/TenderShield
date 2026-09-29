"""Renders the demonstration tender package (tender notice, bids, compliance documents)
into real PDF files so the ingestion pipeline exercises genuine PDF text extraction."""

from __future__ import annotations

import random
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from .market import gstin
from .scenario import DEMO_TENDER, PARAPHRASE, SECTION_BANKS

FONT = "Helvetica"
FONT_SIZE = 9.5
LEADING = 13.5
MARGIN = 56


def write_pdf(path: Path, title: str, pages: list[list[str]]) -> int:
    """Write one PDF page per entry in ``pages``. Returns the page count.

    ``invariant=1`` makes the byte output deterministic, so document hashes are stable
    across regenerations - a requirement for the evidence-integrity demo.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = A4
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    pdf.setTitle(title)
    pdf.setAuthor("TenderShield Nexus demo generator")
    total = len(pages)
    for number, lines in enumerate(pages, start=1):
        pdf.setFont(FONT + "-Bold", 8)
        pdf.drawString(MARGIN, height - 36, title[:110])
        y = height - MARGIN - 10
        for line in lines:
            bold = line.startswith("## ")
            text = line[3:] if bold else line
            pdf.setFont(FONT + "-Bold" if bold else FONT, FONT_SIZE + (1.5 if bold else 0))
            wrapped = simpleSplit(text, FONT, FONT_SIZE, width - 2 * MARGIN) if text else [""]
            for part in wrapped:
                if y < MARGIN + 20:
                    raise ValueError(f"Content overflows page {number} of {path.name}")
                pdf.drawString(MARGIN, y, part)
                y -= LEADING
        pdf.setFont(FONT, 8)
        pdf.drawString(width / 2 - 25, 30, f"Page {number} of {total}")
        pdf.showPage()
    pdf.save()
    return total


# --- Tender notice ------------------------------------------------------------------

def tender_pages() -> list[list[str]]:
    t = DEMO_TENDER
    return [
        [
            "## NAVI MUMBAI MUNICIPAL CORPORATION",
            "## Transport Engineering Department",
            "",
            f"## Notice Inviting Tender No. {t['tender_id']}",
            "",
            t["title"],
            "",
            f"Estimated contract value: Rs. {t['estimated_value_cr']:.2f} crore",
            f"Date of publication: {t['published_on']}",
            "Mode of procurement: Open tender, two-envelope system (technical and financial)",
            "",
            "## 1. General",
            "1.1 The Corporation invites online bids from eligible bidders for the works described in this document.",
            "1.2 The tender document comprises the notice, eligibility criteria, scope of work, instructions to bidders and the draft contract.",
            "1.3 Bidders are advised to study the complete document carefully before submitting their bids.",
        ],
        [
            "## 2. Scope of Work",
            "2.1 Survey, design, supply and installation of adaptive traffic signal controllers at 120 junctions.",
            "2.2 Establishment of an Integrated Traffic Management Command Centre with video wall and analytics.",
            "2.3 Road marking, pedestrian crossings and junction geometry improvement at identified locations.",
            "2.4 Integration with the existing e-challan and city surveillance systems.",
            "2.5 Operation and maintenance of the complete system for a period of five years after acceptance.",
        ],
        [
            "## 3. Financial Eligibility",
            "3.1 The Bidder shall have an average annual turnover of not less than Rs. 10 crore during the last three "
            "financial years (FY 2022-23 to FY 2024-25), duly certified by a Chartered Accountant.",
            "3.2 The Bidder shall have a positive net worth as per the audited balance sheet of FY 2024-25.",
            "3.3 The Bidder shall submit a solvency certificate from a scheduled bank for an amount not less than Rs. 4 crore.",
        ],
        [
            "## 4. Technical Eligibility",
            "4.1 The Bidder shall have been in operation for at least five years as on the date of bid submission.",
            "4.2 The Bidder shall have completed at least three similar projects during the preceding five years with "
            "an aggregate value not less than Rs. 10 crore.",
            "4.3 The Bidder shall have not less than 25 technical personnel on its payroll.",
        ],
        [
            "## 5. Certifications",
            "5.1 The Bidder must possess a valid ISO 9001:2015 quality management certificate, which shall be valid on "
            "the date of bid submission.",
            "5.2 Possession of a valid ISO/IEC 27001 information security certificate is desirable and will be "
            "considered favourably.",
        ],
        [
            "## 6. Statutory and Integrity Requirements",
            "6.1 The Bidder shall be registered under the Goods and Services Tax (GST) Act and furnish its GSTIN.",
            "6.2 The Bidder shall furnish a copy of its Permanent Account Number (PAN) card.",
            "6.3 The Bidder shall not have been blacklisted or debarred by any Central or State Government "
            "department or PSU.",
            "6.4 The Bidder shall disclose the names and Director Identification Numbers (DIN) of all its "
            "directors and beneficial owners.",
            "6.5 The bid shall be signed by an authorised signatory holding a valid Power of Attorney.",
            "6.6 Micro and Small Enterprises claiming exemption from EMD shall submit a valid Udyam registration "
            "certificate.",
        ],
        [
            "## 7. Bid Submission",
            "7.1 The Bidder shall submit an Earnest Money Deposit (EMD) of Rs. 20 lakh through the e-procurement portal.",
            "7.2 Bids must be submitted on or before 15 March 2026, 15:00 hrs IST. Late bids shall be rejected.",
            "7.3 Bids shall remain valid for a period of not less than 180 days from the bid due date.",
        ],
        [
            "## 8. Evaluation and Award",
            "8.1 Technical bids will be evaluated first; financial bids of technically qualified bidders alone will be opened.",
            "8.2 The contract will be awarded to the lowest evaluated technically qualified bidder (L1).",
            "8.3 The Corporation reserves the right to accept or reject any bid without assigning reasons.",
        ],
    ]


# --- Bidder compliance documents ----------------------------------------------------

def _amount(value: float, unit: str) -> str:
    return f"Rs. {value:.2f} {unit}"


def compliance_pages(vendor: dict, facts: dict) -> list[list[str]]:
    gstin_no = gstin(vendor["state_code"], vendor["pan"])
    iso27 = (
        f"ISO/IEC 27001 Certificate - Valid Until: {facts['iso27001_valid_until']}"
        if facts.get("iso27001_valid_until")
        else "ISO/IEC 27001 Certificate: Not held"
    )
    declarations = [
        "## Section D - Statutory Registrations and Declarations",
        f"GST Registration: {'Registered' if facts['gst_registered'] else 'Not registered'} (GSTIN {gstin_no})",
        f"PAN: {vendor['pan']} (copy enclosed)" if facts["pan_available"] else "PAN: Not furnished",
        "Blacklisting / Debarment Declaration: "
        + ("Blacklisted" if facts["blacklisted"] else "Not blacklisted or debarred by any authority"),
    ]
    if facts.get("ownership_disclosure"):
        declarations.append("Ownership Disclosure: Submitted - directors listed below")
        declarations += [f"Director: {d['name']} (DIN {d['din']})" for d in vendor["directors"]]
    declarations += [
        f"Power of Attorney: {'Submitted' if facts['power_of_attorney'] else 'Not submitted'} in favour of authorised signatory",
        f"MSME Exemption Claimed: {'Yes' if facts['claims_msme_exemption'] else 'No'}",
    ]
    if facts.get("claims_msme_exemption") and facts.get("udyam_registered"):
        declarations.append(f"Udyam Registration: UDYAM-{vendor['state_code']}-02-00{vendor['pan'][5:9]}")

    return [
        [
            f"## {vendor['name']}",
            f"Compliance documents for Tender {DEMO_TENDER['tender_id']}",
            "",
            "## Section A - Financial Capacity",
            "Average Annual Turnover (FY 2022-23 to FY 2024-25): " + _amount(facts["avg_annual_turnover_cr"], "crore"),
            "Net Worth (Audited, FY 2024-25): " + _amount(facts["net_worth_cr"], "crore"),
            "Solvency Certificate Amount: " + _amount(facts["solvency_amount_cr"], "crore"),
            "Certified by: M/s Kapoor & Associates, Chartered Accountants",
        ],
        [
            "## Section B - Experience and Resources",
            f"Years in Operation (as on bid date): {facts['years_in_operation']}",
            f"Similar Projects Completed in Preceding Five Years: {facts['similar_projects_5y']}",
            "Aggregate Value of Similar Projects: " + _amount(facts["similar_projects_value_cr"], "crore"),
            f"Technical Personnel on Payroll: {facts['technical_staff']}",
        ],
        [
            "## Section C - Certifications",
            f"ISO 9001:2015 Certificate No. QMS/{vendor['pan'][:5]}/21 - Valid Until: {facts['iso9001_valid_until']}",
            iso27,
        ],
        declarations,
        [
            "## Section E - Bid Security and Validity",
            f"Earnest Money Deposit: {_amount(facts['emd_amount_lakh'], 'lakh')} (e-payment reference EMD-{vendor['vendor_id']}-0314)",
            f"Bid Validity: {facts['bid_validity_days']} days from bid due date",
        ],
    ]


# --- Bidder technical proposals -----------------------------------------------------

def _paraphrase(text: str) -> str:
    for old, new in PARAPHRASE.items():
        text = text.replace(old, new)
    return text


def technical_sections(vendors: list[dict], seed: int) -> dict[str, dict[str, list[str]]]:
    """Choose the sentences each bidder's technical proposal uses, per section.

    Vendor A and Vendor B share a lightly reworded copy of the same text; every other
    bidder draws independently from the common industry phrasing bank.
    """
    rng = random.Random(seed)
    chosen: dict[str, dict[str, list[str]]] = {}
    for vendor in vendors:
        vid = vendor["vendor_id"]
        chosen[vid] = {}
        for section, bank in SECTION_BANKS.items():
            if vid == "V002":
                source = chosen["V001"][section]
                chosen[vid][section] = [_paraphrase(s) for s in source]
            else:
                chosen[vid][section] = rng.sample(bank, 5)
    return chosen


def technical_pages(vendor: dict, facts: dict, sections: dict[str, list[str]], seed: int) -> list[list[str]]:
    rng = random.Random(f"{seed}-{vendor['vendor_id']}")
    pm = rng.choice(["S. Patil", "R. Menon", "K. Bose", "A. Khan", "P. Reddy", "M. Gill"])
    pages = [
        [
            f"## {vendor['name']}",
            f"Technical Proposal - Tender {DEMO_TENDER['tender_id']}",
            "",
            "## 1. Company Profile",
            f"{vendor['name']} was incorporated on {vendor['incorporated']} and has been in operation for "
            f"{facts['years_in_operation']} years.",
            f"The firm has completed {facts['similar_projects_5y']} projects of a similar nature in the preceding five "
            f"years and employs {facts['technical_staff']} technical personnel.",
            f"Registered office: {vendor['registered_address']}.",
        ]
    ]
    for number, (section, sentences) in enumerate(sections.items(), start=2):
        pages.append([f"## {number}. {section}", *sentences])
    engineers, om_team = max(4, facts["technical_staff"] // 6), max(6, facts["technical_staff"] // 4)
    team_variants = [
        [f"{pm} will serve as Project Manager with overall responsibility for delivery.",
         f"{engineers} site engineers report to zone leads covering civil, electrical and ITS works.",
         f"An operations cell of {om_team} staff will run the command centre after acceptance."],
        [f"Delivery is headed by {pm}, who reports directly to our board.",
         f"The field organisation comprises {engineers} engineers grouped into installation crews.",
         f"Maintenance support of {om_team} technicians is planned for the O&M period."],
        [f"Key personnel: {pm} (Project Manager), a certified traffic engineer and a network architect.",
         f"Resources: {engineers} engineers and {om_team} maintenance staff drawn from the permanent payroll."],
    ]
    if vendor["vendor_id"] == "V002":
        team = [_paraphrase(line) for line in team_variants[0]]
    else:
        team = team_variants[rng.randrange(len(team_variants))]
    pages.append([f"## {len(sections) + 2}. Team Structure", *team])
    return pages


def submission_log_pages(rows: list[tuple[str, str, str, float]]) -> list[list[str]]:
    lines = [
        f"## e-Procurement Portal - Bid Submission Log - {DEMO_TENDER['tender_id']}",
        f"Bid submission deadline: {DEMO_TENDER['bid_deadline']}",
        "",
        "Vendor ID | Bidder | Submitted At | Quoted Amount",
    ]
    for vendor_id, name, submitted_at, amount in rows:
        lines.append(f"{vendor_id} | {name} | {submitted_at} | Rs. {amount:.2f} crore")
    return [lines]
