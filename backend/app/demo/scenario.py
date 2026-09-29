"""Hand-authored facts for the demonstration tender TN-2026-014.

The current tender has six bidders. The planted scenarios (spec section 27) are:
  * Vendor A + Vendor B  - shared director and premises, a cover-bidding ring with a
                           winner/runner-up rotation, and near-identical bid documents.
  * Vendor C + Vendor D  - shared independent director only; they work in different
                           markets, rarely meet, and write different documents.
  * Vendor E             - ISO 9001 certificate expired before the bid date (deterministic FAIL).
  * Vendor F             - director / ownership information unavailable (UNKNOWN).

Around them, ``market.py`` builds a registry of ~180 contractors across eight regional
markets and ``history.py`` simulates five years of award records. The background
contains the kind of structure real procurement data has - group companies, independent
directors on several boards, virtual-office addresses, a shared bid consultant, a
debarred firm reborn under a new name, dominant national players - plus two more
collusive rings that do not touch the current tender. Those planted background actors
are defined here (V007-V026) so that every demo relationship is reproducible.
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

# Market profile of each current bidder, used by the history simulator.
#   regions:    markets the firm bids in routinely
#   outstation: markets it enters only for large contracts (min_value_cr and above)
#   propensity: probability of bidding on an eligible tender
#   price_bias: the firm's habitual quote relative to the market (negative = aggressive)
BIDDER_PROFILES = {
    "V001": {"constitution": "Private Limited Company", "cin": "U45200MH2011PTC219874", "segments": ["ITS", "ROADS"],
             "home_region": "MMR", "regions": ["MMR"], "outstation": {"regions": ["PUNE"], "min_value_cr": 15},
             "turnover_cr": 12.4, "propensity": 0.34, "price_bias": -0.01, "contractor_class": "Class I-A (PWD Maharashtra)"},
    "V002": {"constitution": "Private Limited Company", "cin": "U45400MH2014PTC251930", "segments": ["ITS", "ROADS"],
             "home_region": "MMR", "regions": ["MMR"], "outstation": None,
             "turnover_cr": 11.8, "propensity": 0.30, "price_bias": 0.0, "contractor_class": "Class I-A (PWD Maharashtra)"},
    "V003": {"constitution": "Private Limited Company", "cin": "U45201TN2006PTC060412", "segments": ["ITS", "ROADS"],
             "home_region": "CHENNAI", "regions": ["CHENNAI"], "outstation": {"regions": ["MMR", "BENGALURU"], "min_value_cr": 25},
             "turnover_cr": 15.2, "propensity": 0.38, "price_bias": 0.01, "contractor_class": "Class I (TNPWD)"},
    "V004": {"constitution": "Public Limited Company", "cin": "U45309TG2017PLC120655", "segments": ["ITS", "ELEC"],
             "home_region": "HYDERABAD", "regions": ["HYDERABAD"], "outstation": {"regions": ["MMR", "BENGALURU"], "min_value_cr": 25},
             "turnover_cr": 10.9, "propensity": 0.36, "price_bias": 0.02, "contractor_class": "Special Class (Telangana R&B)"},
    "V005": {"constitution": "Private Limited Company", "cin": "U45202MH2013PTC241187", "segments": ["ITS", "ROADS"],
             "home_region": "MMR", "regions": ["MMR", "PUNE"], "outstation": None,
             "turnover_cr": 13.6, "propensity": 0.26, "price_bias": -0.02, "contractor_class": "Class I-A (PWD Maharashtra)"},
    "V006": {"constitution": "Limited Liability Partnership", "cin": "LLPIN AAP-7421", "segments": ["ITS"],
             "home_region": "BENGALURU", "regions": ["BENGALURU"], "outstation": {"regions": ["MMR", "HYDERABAD"], "min_value_cr": 25},
             "turnover_cr": 10.2, "propensity": 0.34, "price_bias": 0.0, "contractor_class": "Class I (Karnataka PWD)"},
}


def _v(vendor_id, name, pan, state_code, address, phone, email, incorporated, directors, profile, msme=False):
    return {"vendor_id": vendor_id, "alias": None, "name": name, "pan": pan, "state_code": state_code,
            "registered_address": address, "phone": phone, "email": email, "incorporated": incorporated, "msme": msme,
            "directors": directors, "profile": profile}


def _profile(constitution, cin, segments, home, regions, turnover, propensity, outstation=None, price_bias=0.0,
             contractor_class="Class I (State PWD)", **extra):
    return {"constitution": constitution, "cin": cin, "segments": segments, "home_region": home, "regions": regions,
            "outstation": outstation, "turnover_cr": turnover, "propensity": propensity, "price_bias": price_bias,
            "contractor_class": contractor_class, **extra}


PVT, PUB, LLP = "Private Limited Company", "Public Limited Company", "Limited Liability Partnership"

# Directors reused across the planted network (same person = same DIN).
RAJESH = {"name": "Rajesh Kumar Sharma", "din": "07345128", "role": "Director"}
SUNITA = {"name": "Sunita R. Sharma", "din": "08650231", "role": "Designated Partner"}
MEERA = {"name": "Meera Iyer", "din": "06543219", "role": "Independent Director"}
SANDEEP_KALE = {"name": "Sandeep Kale", "din": "07811452", "role": "Director"}
VIVEK = {"name": "Vivek Malhotra", "din": "01928374", "role": "Managing Director"}
VENKATESH = {"name": "Dr. Venkatesh Subramanian", "din": "02468013", "role": "Independent Director"}
BHATNAGAR = {"name": "Anil Kumar Bhatnagar", "din": "03157920", "role": "Independent Director"}
MAHALAXMI_DIRS = [{"name": "Ganesh Pawar", "din": "06120457", "role": "Director"},
                  {"name": "Shubhangi Pawar", "din": "06120458", "role": "Director"}]

THANE_VIRTUAL_OFFICE = "Office No. 5, 2nd Floor, Siddhivinayak Chambers, Gokhale Road, Naupada, Thane West, Maharashtra 400602"
TRIDENT_HQ = "A-42, Okhla Industrial Area Phase II, New Delhi, Delhi 110020"

# Hand-authored background actors. Everything else in the registry is generated.
PLANTED_VENDORS = [
    # --- Around the Vendor A / Vendor B ring -------------------------------------------
    _v("V007", "Shreeji Traffic Solutions LLP", "AAKFS2291E", "27",
       "Room No. 7, Sai Darshan CHS, Sector 9, Vashi, Navi Mumbai, Maharashtra 400703",
       "+91 22 2789 4432",  # the same landline as Vendor B
       "shreejitraffic@gmail.com", "2019-02-11",
       [SUNITA, {"name": "Kiran Patkar", "din": "08650232", "role": "Designated Partner"}],
       _profile(LLP, "LLPIN AAO-1187", ["ITS"], "MMR", ["MMR"], 1.6, 0.02, role="cover bidder in the A/B ring"), msme=True),
    _v("V008", "Sharma Realty Developers Pvt. Ltd.", "AAHCS8812L", "27",
       "Flat 1202, Palm Beach Residency, Sector 42, Nerul, Navi Mumbai, Maharashtra 400706",
       "+91 98200 41177", "office@sharmarealty.in", "2009-10-05",
       [RAJESH, SUNITA],
       _profile(PVT, "U70100MH2009PTC196645", ["BLDG"], "MMR", ["MMR"], 6.5, 0.04,
                role="family company of Vendor A's director; links him to the Shreeji cover bidder")),
    # --- Pune road-works ring (three firms, round-robin) ------------------------------
    _v("V009", "Kale Constructions Pvt. Ltd.", "AAECK5530P", "27",
       "S. No. 44/2, Paud Road, Kothrud, Pune, Maharashtra 411038", "+91 20 2538 6120", "tenders@kaleconstructions.in",
       "2008-04-21", [SANDEEP_KALE, {"name": "Rohini Kale", "din": "07811453", "role": "Director"}],
       _profile(PVT, "U45200PN2008PTC131902", ["ROADS", "DRAIN"], "PUNE", ["PUNE"], 22.0, 0.30)),
    _v("V010", "Deshmukh Infra Projects Pvt. Ltd.", "AAFCD7718H", "27",
       "Office No. 12, Shivam Business Centre, Karve Road, Kothrud, Pune, Maharashtra 411038", "+91 20 2546 0931",
       "contracts@deshmukhinfra.com", "2012-09-14",
       [{"name": "Amol Deshmukh", "din": "05522904", "role": "Director"},
        {"name": "Vaishali Deshmukh", "din": "05522905", "role": "Director"}],
       _profile(PVT, "U45400PN2012PTC144310", ["ROADS"], "PUNE", ["PUNE"], 18.5, 0.30)),
    _v("V011", "Sahyadri Roadways LLP", "AAKFS6043Q", "27",
       "Office 12, Shivam Business Centre, Karve Road, Kothrud, Pune 411038", "+91 20 2546 0990",
       "sahyadriroadways@gmail.com", "2016-06-30",
       [SANDEEP_KALE, {"name": "Nitin Jagtap", "din": "07102266", "role": "Designated Partner"}],
       _profile(LLP, "LLPIN AAG-5530", ["ROADS"], "PUNE", ["PUNE"], 9.0, 0.30)),
    # --- Nagpur street-lighting pair, both filed by the same bid consultant -----------
    _v("V012", "Vidarbha Electro Engineers Pvt. Ltd.", "AADCV3302F", "27",
       "Plot No. 61, Hingna MIDC, Nagpur, Maharashtra 440016", "+91 712 229 4410", "vidarbhaelectro@tenderdesk.in",
       "2010-01-19", [{"name": "Prashant Wankhede", "din": "03390117", "role": "Director"},
                      {"name": "Minal Wankhede", "din": "03390118", "role": "Director"}],
       _profile(PVT, "U31900MH2010PTC199804", ["ELEC"], "NAGPUR", ["NAGPUR"], 7.5, 0.30)),
    _v("V013", "Orange City Power Solutions Pvt. Ltd.", "AAFCO9021K", "27",
       "204, Shriram Towers, Kingsway, Civil Lines, Nagpur, Maharashtra 440001", "+91 712 256 8702",
       "orangecitypower@tenderdesk.in", "2015-08-03",
       [{"name": "Rahul Thakre", "din": "07230981", "role": "Director"},
        {"name": "Snehal Bhoyar", "din": "07230982", "role": "Director"}],
       _profile(PVT, "U40106MH2015PTC267430", ["ELEC"], "NAGPUR", ["NAGPUR"], 5.8, 0.30)),
    _v("V014", "Godavari Lighting Solutions LLP", "AAKFG1178M", "27",
       "Plot C-17, Satpur MIDC, Nashik, Maharashtra 422007", "+91 253 235 1044", "godavarilighting@tenderdesk.in",
       "2018-11-12", [{"name": "Tushar Bhamre", "din": "08301145", "role": "Designated Partner"},
                      {"name": "Manisha Ahire", "din": "08301146", "role": "Designated Partner"}],
       _profile(LLP, "LLPIN AAN-3321", ["ELEC"], "NASHIK", ["NASHIK"], 3.4, 0.28,
                role="uses the same bid consultant as V012 / V013; no collusion planted"), msme=True),
    # --- Legitimate group companies: common directors, same head office, never co-bid -
    _v("V015", "Trident Infrastructure Ltd.", "AABCT4410D", "07", TRIDENT_HQ, "+91 11 4165 2200",
       "tenders@tridentgroup.in", "1996-02-27",
       [VIVEK, {"name": "Ritu Malhotra", "din": "01928375", "role": "Director"}, VENKATESH],
       _profile(PUB, "L45201DL1996PLC077120", ["ROADS", "WATER"], "NCR",
                ["MMR", "PUNE", "NAGPUR", "GUJARAT", "HYDERABAD"], 640.0, 0.22, price_bias=-0.01,
                contractor_class="Class AA (CPWD)", min_value_cr=20)),
    _v("V016", "Trident Smart Systems Pvt. Ltd.", "AADCT7753J", "07", TRIDENT_HQ, "+91 11 4165 2290",
       "its@tridentgroup.in", "2015-07-01",
       [VIVEK, {"name": "Karan Malhotra", "din": "07119034", "role": "Director"}],
       _profile(PVT, "U72900DL2015PTC281563", ["ITS"], "NCR", ["MMR", "PUNE", "GUJARAT", "BENGALURU"], 85.0, 0.22,
                min_value_cr=12)),
    # --- Dominant national ITS players: meet in most big tenders, genuinely compete ---
    _v("V017", "Orion Smart Mobility Ltd.", "AABCO6674R", "06",
       "Tower B, 7th Floor, Vatika Business Park, Sector 49, Gurugram, Haryana 122018", "+91 124 470 9900",
       "bids@orionmobility.com", "2004-05-10",
       [{"name": "Siddharth Kapoor", "din": "00987612", "role": "Managing Director"},
        {"name": "Neelam Kapoor", "din": "00987613", "role": "Director"}, BHATNAGAR],
       _profile(PUB, "U74899HR2004PLC041297", ["ITS"], "NCR",
                ["MMR", "PUNE", "NAGPUR", "GUJARAT", "CHENNAI", "HYDERABAD", "BENGALURU"], 420.0, 0.62,
                price_bias=0.02, contractor_class="Empanelled system integrator (MoHUA)", min_value_cr=10)),
    _v("V018", "Quantum Traffic Systems Ltd.", "AABCQ2209N", "29",
       "No. 88, 4th Cross, Peenya Industrial Area, Bengaluru, Karnataka 560058", "+91 80 2839 5510",
       "tenders@quantumtraffic.co.in", "2002-12-02",
       [{"name": "Harish Gowda", "din": "01045566", "role": "Managing Director"}, VENKATESH,
        {"name": "Lakshmi Hegde", "din": "01045567", "role": "Director"}],
       _profile(PUB, "U31909KA2002PLC031174", ["ITS"], "BENGALURU",
                ["BENGALURU", "CHENNAI", "HYDERABAD", "MMR", "PUNE"], 310.0, 0.60,
                price_bias=0.015, contractor_class="Empanelled system integrator (MoHUA)", min_value_cr=10)),
    # --- Vendor C / D's independent director also sits on these boards -----------------
    _v("V019", "Kaveri Water Infrastructure Ltd.", "AABCK3398G", "33",
       "15, Anna Salai, Guindy, Chennai, Tamil Nadu 600032", "+91 44 2250 7781", "projects@kaveriwater.in",
       "1999-03-15", [{"name": "R. Krishnan", "din": "00561290", "role": "Managing Director"}, MEERA],
       _profile(PUB, "U45203TN1999PLC041876", ["WATER"], "CHENNAI", ["CHENNAI", "BENGALURU"], 140.0, 0.3)),
    _v("V020", "Charminar Power Projects Ltd.", "AABCC7120B", "36",
       "6-3-1109, Raj Bhavan Road, Somajiguda, Hyderabad, Telangana 500082", "+91 40 2331 0904",
       "tenders@charminarpower.com", "2003-07-22",
       [{"name": "Srinivas Reddy", "din": "00872311", "role": "Managing Director"}, MEERA],
       _profile(PUB, "U40109TG2003PLC041552", ["ELEC"], "HYDERABAD", ["HYDERABAD"], 95.0, 0.3)),
    # --- Four unrelated small firms registered at one virtual-office address -----------
    _v("V021", "Vighnaharta Civil Works Pvt. Ltd.", "AAGCV5561C", "27", THANE_VIRTUAL_OFFICE, "+91 98191 22034",
       "vighnahartacivil@gmail.com", "2018-03-08",
       [{"name": "Mahesh Gaikwad", "din": "08044120", "role": "Director"},
        {"name": "Swati Gaikwad", "din": "08044121", "role": "Director"}],
       _profile(PVT, "U45309MH2018PTC306612", ["DRAIN"], "MMR", ["MMR"], 3.2, 0.28), msme=True),
    _v("V022", "Aarya Electricals Pvt. Ltd.", "AAJCA2034T", "27", THANE_VIRTUAL_OFFICE, "+91 97699 04512",
       "aaryaelectricals@yahoo.com", "2017-01-25",
       [{"name": "Omkar Naik", "din": "07711904", "role": "Director"},
        {"name": "Prerna Naik", "din": "07711905", "role": "Director"}],
       _profile(PVT, "U31900MH2017PTC289040", ["ELEC"], "MMR", ["MMR"], 2.6, 0.28), msme=True),
    _v("V023", "Neelkanth Aqua Projects LLP", "AAKFN8806A", "27", THANE_VIRTUAL_OFFICE, "+91 90040 77318",
       "neelkanthaqua@gmail.com", "2020-09-17",
       [{"name": "Deepak Chavan", "din": "08870342", "role": "Designated Partner"},
        {"name": "Yogesh Salvi", "din": "08870343", "role": "Designated Partner"}],
       _profile(LLP, "LLPIN AAT-9054", ["WATER"], "MMR", ["MMR"], 2.1, 0.26), msme=True),
    _v("V024", "Pratik Buildcon Pvt. Ltd.", "AAHCP4471W", "27", THANE_VIRTUAL_OFFICE, "+91 98670 51290",
       "pratikbuildcon@gmail.com", "2016-05-02",
       [{"name": "Pratik Mhatre", "din": "07509813", "role": "Director"},
        {"name": "Jayesh Mhatre", "din": "07509814", "role": "Director"}],
       _profile(PVT, "U45200MH2016PTC279932", ["BLDG"], "MMR", ["MMR"], 4.4, 0.26), msme=True),
    # --- Debarred in 2024; the same directors reappear through a new company ----------
    _v("V025", "Mahalaxmi Infracon Pvt. Ltd.", "AAFCM6120E", "27",
       "Plot No. 9, Bhosari MIDC, Pimpri-Chinchwad, Pune, Maharashtra 411026", "+91 20 2712 3380",
       "mahalaxmiinfracon@rediffmail.com", "2007-11-06", MAHALAXMI_DIRS,
       _profile(PVT, "U45200PN2007PTC130775", ["ROADS", "DRAIN"], "PUNE", ["PUNE"], 16.0, 0.30,
                active_until="2024-02-15",
                debarment={"by": "Pune Municipal Corporation", "from": "2024-02-15", "years": 3,
                           "reason": "Submission of forged work-completion certificate"})),
    _v("V026", "Mahalaxmi Urban Solutions Pvt. Ltd.", "AAJCM0457H", "27",
       "Office 310, Kohinoor Plaza, Chinchwad, Pune, Maharashtra 411019", "+91 20 2745 6612",
       "tenders@mahalaxmiurban.in", "2024-04-10", MAHALAXMI_DIRS,
       _profile(PVT, "U45309PN2024PTC229871", ["ROADS", "DRAIN"], "PUNE", ["PUNE"], 11.0, 0.34,
                role="incorporated two months after V025 was debarred")),
]

# Collusive rings planted in the award history. In each ring tender every member bids;
# the designated winner rotates, the others place cover bids a little higher and file
# within minutes of it. ``covers`` join some ring tenders as extra cover bidders only.
RINGS = [
    {"key": "A-B", "members": ["V001", "V002"], "covers": ["V007"], "cover_joins": 5, "region": "MMR",
     "segment": "ITS", "tenders": 9, "outsider_wins": 1, "value_cr": (8.0, 45.0),
     "period": ("2021-03-01", "2025-12-20"), "cover_gap": (0.012, 0.03), "filing_gap_min": (3, 12)},
    {"key": "PUNE-ROADS", "members": ["V009", "V010", "V011"], "covers": [], "cover_joins": 0, "region": "PUNE",
     "segment": "ROADS", "tenders": 12, "outsider_wins": 1, "value_cr": (3.0, 28.0),
     "period": ("2022-01-10", "2025-11-30"), "cover_gap": (0.015, 0.04), "filing_gap_min": (6, 25)},
    {"key": "NAGPUR-LIGHTING", "members": ["V012", "V013"], "covers": [], "cover_joins": 0, "region": "NAGPUR",
     "segment": "ELEC", "tenders": 8, "outsider_wins": 0, "value_cr": (1.2, 9.0),
     "period": ("2021-07-01", "2025-09-30"), "cover_gap": (0.018, 0.035), "filing_gap_min": (2, 9)},
]

# Genuine (competitive) meetings forced into the history: Vendor C and Vendor D met once.
MEETINGS = [{"vendors": ["V003", "V004"], "region": "BENGALURU", "segment": "ITS", "count": 1,
             "value_cr": (28.0, 40.0), "period": ("2023-06-01", "2023-12-31")}]

# Pairs that never bid against each other outside the planted tenders above: ring
# members avoid genuine competition, and group companies do not bid against each other.
EXCLUSIVE_PAIRS = [
    ("V001", "V002"), ("V001", "V007"), ("V002", "V007"), ("V009", "V010"), ("V009", "V011"), ("V010", "V011"),
    ("V012", "V013"), ("V003", "V004"), ("V015", "V016"), ("V025", "V026"),
]

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
