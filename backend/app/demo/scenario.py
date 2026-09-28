"""Hand-authored facts for the demonstration tender TN-2026-014.

The planted scenarios (spec section 27):
  * Vendor A + Vendor B  - shared director and address, repeated co-bidding with a
                           winner/runner-up rotation and near-identical bid documents.
  * Vendor C + Vendor D  - shared director only; rarely bid together, different documents.
  * Vendor E             - ISO 9001 certificate expired before the bid date (deterministic FAIL).
  * Vendor F             - director / ownership information unavailable (UNKNOWN).
"""

from __future__ import annotations

DEMO_TENDER_ID = "TN-2026-014"

DEMO_TENDER = {
    "tender_id": DEMO_TENDER_ID,
    "title": "Design, Supply, Installation and O&M of Integrated Traffic Management System (ITMS) and Smart Road Works",
    "department": "Navi Mumbai Municipal Corporation - Transport Engineering Department",
    "estimated_value_cr": 50.0,
    "published_on": "2026-02-02",
    "bid_deadline": "2026-03-15T15:00:00+05:30",
    "status": "UNDER_EVALUATION",
}

# Current bidders. vendor_id values are the master-registry identifiers.
BIDDERS = [
    {
        "vendor_id": "V001",
        "alias": "Vendor A",
        "name": "Apex Infra Constructions Pvt. Ltd.",
        "pan": "AAKCA4821M",
        "state_code": "27",
        "registered_address": "Plot No. 14, Sector 5, Vashi, Navi Mumbai, Maharashtra 400703",
        "phone": "+91 22 2789 4410",
        "email": "tenders@apexinfra.in",
        "incorporated": "2011-06-18",
        "msme": False,
        "directors": [
            {"name": "Rajesh Kumar Sharma", "din": "07345128"},
            {"name": "Anita Desai", "din": "08112345"},
        ],
    },
    {
        "vendor_id": "V002",
        "alias": "Vendor B",
        "name": "Bharat Buildcon Private Limited",
        "pan": "AAFCB7730Q",
        "state_code": "27",
        # Same premises as Vendor A, written differently.
        "registered_address": "Plot 14, Sec-5, Vashi, Navi Mumbai - 400703",
        "phone": "+91 22 2789 4432",
        "email": "bids@bharatbuildcon.co.in",
        "incorporated": "2014-01-09",
        "msme": False,
        "directors": [
            # Same person as Vendor A's director (same DIN), abbreviated name.
            {"name": "Rajesh K. Sharma", "din": "07345128"},
            {"name": "Vikram Joshi", "din": "08876501"},
        ],
    },
    {
        "vendor_id": "V003",
        "alias": "Vendor C",
        "name": "Coastal Engineering Works Pvt Ltd",
        "pan": "AADCC1942K",
        "state_code": "33",
        "registered_address": "No. 22, Greams Road, Thousand Lights, Chennai, Tamil Nadu 600006",
        "phone": "+91 44 2829 1180",
        "email": "contracts@coastalengg.com",
        "incorporated": "2006-08-01",
        "msme": True,
        "directors": [
            {"name": "Meera Iyer", "din": "06543219"},
            {"name": "Suresh Nair", "din": "07120984"},
        ],
    },
    {
        "vendor_id": "V004",
        "alias": "Vendor D",
        "name": "Deccan Projects Limited",
        "pan": "AAECD5518H",
        "state_code": "36",
        "registered_address": "8-2-293/82, Road No. 10, Banjara Hills, Hyderabad, Telangana 500034",
        "phone": "+91 40 2354 7765",
        "email": "tender.cell@deccanprojects.in",
        "incorporated": "2017-11-20",
        "msme": False,
        "directors": [
            {"name": "Meera Iyer", "din": "06543219"},
            {"name": "Arjun Rao", "din": "08991230"},
        ],
    },
    {
        "vendor_id": "V005",
        "alias": "Vendor E",
        "name": "Everest Civil Contractors Pvt. Ltd.",
        "pan": "AAGCE3307B",
        "state_code": "27",
        "registered_address": "Office 402, Hiranandani Business Park, Powai, Mumbai, Maharashtra 400076",
        "phone": "+91 22 4012 8800",
        "email": "projects@everestcivil.in",
        "incorporated": "2013-03-11",
        "msme": False,
        "directors": [
            {"name": "Farhan Qureshi", "din": "07781204"},
            {"name": "Neha Kulkarni", "din": "08234567"},
        ],
    },
    {
        "vendor_id": "V006",
        "alias": "Vendor F",
        "name": "Falcon Infratech LLP",
        "pan": "AAJFF6624C",
        "state_code": "29",
        "registered_address": "3rd Floor, Prestige Tower, Residency Road, Bengaluru, Karnataka 560025",
        "phone": "+91 80 4110 5522",
        "email": "info@falconinfratech.com",
        "incorporated": "2019-07-01",
        "msme": False,
        # Director / ownership information unavailable in the registry extract.
        "directors": [],
    },
]

# Values the bidders declared in their compliance documents (rendered into PDFs and
# re-extracted from those PDFs by the fact extractor). None = not declared.
BIDDER_FACTS = {
    "V001": {
        "avg_annual_turnover_cr": 12.40, "net_worth_cr": 8.10, "solvency_amount_cr": 5.00,
        "years_in_operation": 14, "similar_projects_5y": 4, "similar_projects_value_cr": 18.60,
        "technical_staff": 42, "iso9001_valid_until": "2027-06-30", "iso27001_valid_until": "2026-11-30",
        "gst_registered": True, "pan_available": True, "blacklisted": False,
        "ownership_disclosure": True, "power_of_attorney": True,
        "claims_msme_exemption": False, "udyam_registered": None,
        "emd_amount_lakh": 20.0, "bid_validity_days": 180,
    },
    "V002": {
        "avg_annual_turnover_cr": 11.80, "net_worth_cr": 6.90, "solvency_amount_cr": 4.50,
        "years_in_operation": 12, "similar_projects_5y": 3, "similar_projects_value_cr": 14.20,
        "technical_staff": 31, "iso9001_valid_until": "2027-02-28", "iso27001_valid_until": None,
        "gst_registered": True, "pan_available": True, "blacklisted": False,
        "ownership_disclosure": True, "power_of_attorney": True,
        "claims_msme_exemption": False, "udyam_registered": None,
        "emd_amount_lakh": 20.0, "bid_validity_days": 180,
    },
    "V003": {
        "avg_annual_turnover_cr": 15.20, "net_worth_cr": 10.40, "solvency_amount_cr": 6.00,
        "years_in_operation": 19, "similar_projects_5y": 5, "similar_projects_value_cr": 26.00,
        "technical_staff": 55, "iso9001_valid_until": "2026-09-30", "iso27001_valid_until": "2027-01-15",
        "gst_registered": True, "pan_available": True, "blacklisted": False,
        "ownership_disclosure": True, "power_of_attorney": True,
        "claims_msme_exemption": True, "udyam_registered": True,
        "emd_amount_lakh": 20.0, "bid_validity_days": 180,
    },
    "V004": {
        "avg_annual_turnover_cr": 10.90, "net_worth_cr": 4.20, "solvency_amount_cr": 4.00,
        "years_in_operation": 8, "similar_projects_5y": 3, "similar_projects_value_cr": 11.50,
        "technical_staff": 28, "iso9001_valid_until": "2026-12-31", "iso27001_valid_until": None,
        "gst_registered": True, "pan_available": True, "blacklisted": False,
        "ownership_disclosure": True, "power_of_attorney": True,
        "claims_msme_exemption": False, "udyam_registered": None,
        "emd_amount_lakh": 20.0, "bid_validity_days": 180,
    },
    "V005": {
        "avg_annual_turnover_cr": 13.60, "net_worth_cr": 7.50, "solvency_amount_cr": 5.50,
        "years_in_operation": 12, "similar_projects_5y": 4, "similar_projects_value_cr": 17.90,
        "technical_staff": 36,
        # Expired before the bid date (2026-03-12) -> deterministic FAIL.
        "iso9001_valid_until": "2026-01-31", "iso27001_valid_until": None,
        "gst_registered": True, "pan_available": True, "blacklisted": False,
        "ownership_disclosure": True, "power_of_attorney": True,
        "claims_msme_exemption": False, "udyam_registered": None,
        "emd_amount_lakh": 20.0, "bid_validity_days": 180,
    },
    "V006": {
        "avg_annual_turnover_cr": 10.20, "net_worth_cr": 3.10, "solvency_amount_cr": 4.20,
        "years_in_operation": 6, "similar_projects_5y": 3, "similar_projects_value_cr": 10.40,
        "technical_staff": 26, "iso9001_valid_until": "2026-08-31", "iso27001_valid_until": None,
        "gst_registered": True, "pan_available": True, "blacklisted": False,
        # Ownership disclosure not furnished -> UNKNOWN / INSUFFICIENT DATA.
        "ownership_disclosure": None, "power_of_attorney": True,
        "claims_msme_exemption": False, "udyam_registered": None,
        "emd_amount_lakh": 20.0, "bid_validity_days": 180,
    },
}

CURRENT_BIDS = {
    # vendor_id: (amount in crore, submission timestamp IST)
    "V001": (48.20, "2026-03-14T16:42:10+05:30"),
    "V002": (49.15, "2026-03-14T16:47:55+05:30"),
    "V003": (50.60, "2026-03-13T11:05:32+05:30"),
    "V004": (53.05, "2026-03-15T10:20:07+05:30"),
    "V005": (47.45, "2026-03-12T18:30:44+05:30"),
    "V006": (51.80, "2026-03-15T14:48:19+05:30"),
}

# Planted pairs for the historical record generator.
COLLUSIVE_PAIR = ("V001", "V002")
COLLUSIVE_COBIDS = 5
WEAK_PAIR = ("V003", "V004")
WEAK_COBIDS = 1

# --- Technical bid sentence banks -------------------------------------------------

SECTION_BANKS: dict[str, list[str]] = {
    "Implementation Methodology": [
        "We will commence with a detailed site survey of all 120 junctions to validate the existing civil and electrical infrastructure.",
        "A phased rollout approach will be adopted, beginning with the 20 highest-density corridors identified by the traffic police.",
        "Our design team will prepare junction-level layouts and submit them for approval within 30 days of the work order.",
        "Adaptive signal controllers will be integrated with the central command platform through an open, standards-based API.",
        "All field equipment will undergo factory acceptance testing before dispatch to site.",
        "Civil works for poles, foundations and ducting will be executed at night to minimise disruption to traffic.",
        "The solution architecture follows a layered model separating field devices, network, data and application tiers.",
        "Video analytics for violation detection will be deployed on edge servers placed at aggregation points.",
        "Integration with the existing e-challan system will be completed during the second implementation phase.",
        "A digital twin of the corridor network will be used to simulate signal timing plans before go-live.",
        "Legacy fixed-time controllers will be retrofitted wherever the cabinet and wiring are in serviceable condition.",
        "Stakeholder workshops will be conducted with the traffic police and municipal engineers at each milestone.",
    ],
    "Risk Management": [
        "Delays in right-of-way permissions are the principal schedule risk and will be tracked in a weekly risk register.",
        "Supply-chain risk for imported controllers is mitigated by maintaining a buffer stock of ten percent.",
        "Monsoon-related civil work interruptions have been factored into the schedule with a float of six weeks.",
        "Cyber-security risks are addressed through network segmentation, hardened devices and periodic penetration testing.",
        "Power outages at field cabinets will be mitigated with online UPS units providing four hours of backup.",
        "Each identified risk is assigned an owner, a probability rating and a documented mitigation plan.",
        "Utility damage during excavation is prevented by ground-penetrating radar surveys before trenching.",
        "Vendor lock-in is avoided by insisting on open protocols such as NTCIP and ONVIF.",
        "Data-privacy risks from camera feeds are controlled through role-based access and automatic retention limits.",
        "Contractor safety risks are managed through daily toolbox talks and a dedicated safety officer on site.",
        "Escalation to the client's project director is triggered for any risk rated high for more than two weeks.",
        "Insurance cover for contractor's all risks will be maintained for the full contract period.",
    ],
    "Deployment Schedule": [
        "Phase 1 covering survey, design approval and pilot junctions will be completed in the first four months.",
        "Phase 2 will extend the deployment to eighty junctions and commission the command centre by month nine.",
        "Phase 3 covers the remaining junctions, system integration and user acceptance testing by month fourteen.",
        "Operational acceptance will be sought after a ninety-day stabilisation period following go-live.",
        "A detailed Gantt chart with critical-path activities is enclosed as Annexure T-4.",
        "Mobilisation of the site team and establishment of the site office will be completed within fifteen days.",
        "Field installation will proceed in parallel crews of four, each responsible for one zone of the city.",
        "Training of municipal operators will be scheduled in the final two months before handover.",
        "Monthly progress reports with earned-value metrics will be submitted to the engineer-in-charge.",
        "The pilot corridor on Palm Beach Road will be used to validate performance before scaling up.",
        "Command centre furniture and video wall installation will be synchronised with software commissioning.",
        "The five-year operations and maintenance period begins immediately after operational acceptance.",
    ],
    "Quality Assurance": [
        "Our quality management system is certified to ISO 9001 and applied across all project activities.",
        "Inspection and test plans will be prepared for every work package and approved before execution.",
        "Third-party inspection of civil works will be arranged at foundation, cabling and commissioning stages.",
        "Non-conformances will be logged, analysed for root cause and closed within seven working days.",
        "Weekly quality audits will be conducted by an independent quality manager reporting to the directors.",
        "Material test certificates will be verified for all structural steel and cable deliveries.",
        "Software releases will pass automated regression testing before deployment to production.",
        "Calibration records for all measuring instruments will be maintained on site.",
        "Handover documentation will include as-built drawings, test reports and operation manuals.",
        "Customer feedback will be collected quarterly and reviewed in management review meetings.",
        "Checklists derived from the Indian Roads Congress guidelines will govern all road restoration works.",
        "A defect liability register will be maintained throughout the warranty period.",
    ],
}

# Light-touch rewording applied to Vendor B's copy of Vendor A's text.
PARAPHRASE = {
    " will ": " shall ",
    "We shall": "We will",
    "Our ": "The ",
    " our ": " the ",
    "detailed": "comprehensive",
    "commence": "begin",
    "minimise": "reduce",
    "weekly": "every week",
    "approximately": "about",
}
