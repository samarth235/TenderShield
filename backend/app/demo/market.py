"""Reference data and the vendor registry for the simulated procurement market (Demo Mode).

The market is modelled on urban-local-body works procurement in western and southern
India: eight regional markets, each with its own buyers (municipal corporations, smart-city
SPVs, development authorities), six work segments with their own value ranges and pricing
behaviour, and a contractor population whose size, specialisation and reach decide which
tenders each firm can and does bid for.

Everything is synthetic and generated from a fixed seed. Company, person and address
records follow real Indian formats (CIN / LLPIN, PAN, GSTIN with a valid check digit, DIN,
six-digit PIN codes) so that entity resolution has to cope with realistic inputs.
"""

from __future__ import annotations

import random
from datetime import date

from rapidfuzz import fuzz

from ..entities.resolution import company_core
from .scenario import BIDDER_PROFILES, BIDDERS, PLANTED_VENDORS

N_REGISTERED_VENDORS = 260

STATE_CODES = {"Maharashtra": "27", "Gujarat": "24", "Tamil Nadu": "33", "Telangana": "36", "Karnataka": "29",
               "Delhi": "07", "Haryana": "06"}
STATE_ABBR = {"Maharashtra": "MH", "Gujarat": "GJ", "Tamil Nadu": "TN", "Telangana": "TG", "Karnataka": "KA",
              "Delhi": "DL", "Haryana": "HR"}

# region -> (state, share of tenders, [(city, [(locality, pin)])])
REGIONS: dict[str, dict] = {
    "MMR": {"state": "Maharashtra", "tender_share": 0.38, "vendor_share": 0.30, "cities": [
        ("Navi Mumbai", [("Vashi", "400703"), ("Nerul", "400706"), ("CBD Belapur", "400614"), ("Airoli", "400708"),
                         ("Kharghar", "410210"), ("Ghansoli", "400701"), ("Sanpada", "400705"), ("Koparkhairane", "400709")]),
        ("Thane", [("Wagle Estate", "400604"), ("Naupada", "400602"), ("Majiwada", "400601"), ("Kolshet Road", "400607")]),
        ("Mumbai", [("Andheri East", "400069"), ("Goregaon East", "400063"), ("Chembur", "400071"), ("Fort", "400001"),
                    ("Lower Parel", "400013"), ("Powai", "400076"), ("Vikhroli West", "400083")]),
        ("Kalyan", [("Khadakpada", "421301"), ("Dombivli East", "421201")]),
        ("Panvel", [("New Panvel", "410206"), ("Kamothe", "410209")]),
    ]},
    "PUNE": {"state": "Maharashtra", "tender_share": 0.17, "vendor_share": 0.16, "cities": [
        ("Pune", [("Shivajinagar", "411005"), ("Baner", "411045"), ("Kothrud", "411038"), ("Hadapsar", "411028"),
                  ("Wakad", "411057"), ("Yerawada", "411006")]),
        ("Pimpri-Chinchwad", [("Bhosari MIDC", "411026"), ("Chinchwad", "411019"), ("Nigdi", "411044")]),
    ]},
    "NASHIK": {"state": "Maharashtra", "tender_share": 0.06, "vendor_share": 0.06, "cities": [
        ("Nashik", [("Satpur MIDC", "422007"), ("College Road", "422005"), ("Ambad", "422010")]),
    ]},
    "NAGPUR": {"state": "Maharashtra", "tender_share": 0.08, "vendor_share": 0.07, "cities": [
        ("Nagpur", [("Dharampeth", "440010"), ("Civil Lines", "440001"), ("Hingna MIDC", "440016"),
                    ("Sadar", "440001"), ("Manish Nagar", "440015")]),
    ]},
    "GUJARAT": {"state": "Gujarat", "tender_share": 0.10, "vendor_share": 0.10, "cities": [
        ("Ahmedabad", [("Navrangpura", "380009"), ("Bodakdev", "380054"), ("Naroda GIDC", "382330")]),
        ("Surat", [("Athwa", "395001"), ("Udhna", "394210")]),
        ("Vadodara", [("Alkapuri", "390007"), ("Makarpura GIDC", "390010")]),
    ]},
    "CHENNAI": {"state": "Tamil Nadu", "tender_share": 0.07, "vendor_share": 0.08, "cities": [
        ("Chennai", [("Guindy", "600032"), ("T. Nagar", "600017"), ("Anna Nagar", "600040"), ("Ambattur", "600058")]),
    ]},
    "HYDERABAD": {"state": "Telangana", "tender_share": 0.08, "vendor_share": 0.08, "cities": [
        ("Hyderabad", [("Madhapur", "500081"), ("Begumpet", "500016"), ("Kukatpally", "500072"), ("Uppal", "500039")]),
    ]},
    "BENGALURU": {"state": "Karnataka", "tender_share": 0.06, "vendor_share": 0.08, "cities": [
        ("Bengaluru", [("Koramangala", "560034"), ("Whitefield", "560066"), ("Jayanagar", "560041"),
                       ("Rajajinagar", "560010")]),
    ]},
}
NCR = {"state": "Delhi", "vendor_share": 0.07, "cities": [
    ("New Delhi", [("Okhla Phase II", "110020"), ("Nehru Place", "110019"), ("Janakpuri", "110058")]),
]}
MARKET_REGIONS = list(REGIONS)

# segment -> value distribution (crore), typical quote relative to estimate, title templates
SEGMENTS: dict[str, dict] = {
    "ITS": {"label": "Traffic & ITS", "median_cr": 14.0, "sigma": 0.75, "range": (1.5, 150.0),
            "discount": -0.03, "spread": 0.045, "share": 0.16, "titles": [
                "Supply, installation, testing and commissioning of adaptive traffic signals at {n} junctions, {loc}",
                "Design, supply and O&M of city surveillance CCTV network ({n} cameras) - {loc} zone",
                "Implementation of Intelligent Traffic Management System (ITMS) Phase {ph} - {city}",
                "Upgradation of traffic signals with solar power back-up at {n} junctions in {loc}",
                "Red-light and speed violation detection system with e-challan integration at {n} locations",
                "Supply and installation of variable message sign boards on arterial roads, {city}",
            ]},
    "ROADS": {"label": "Roads", "median_cr": 7.0, "sigma": 0.8, "range": (0.8, 90.0),
              "discount": -0.08, "spread": 0.05, "share": 0.30, "titles": [
                  "Resurfacing of internal roads in {loc} with DBM and BC",
                  "Cement concretisation of roads in {loc} (Package {ph})",
                  "Improvement of junction geometry and footpaths along the main road at {loc}",
                  "Repairs and strengthening of flyover and ROB at {loc}",
                  "Pothole repairs and asphalting of roads in Ward {w}, {city}",
                  "Widening of road from {loc} to {loc2} including utility shifting",
              ]},
    "DRAIN": {"label": "Storm-water drains", "median_cr": 4.5, "sigma": 0.7, "range": (0.5, 40.0),
              "discount": -0.10, "spread": 0.05, "share": 0.14, "titles": [
                  "Construction of RCC box drain along the arterial road at {loc}",
                  "Desilting and nala training works in {loc} before monsoon {yr}",
                  "Providing and laying storm-water drains in Sector {w}, {loc}",
                  "Reconstruction of damaged culverts and cross drains in Ward {w}, {city}",
              ]},
    "ELEC": {"label": "Street lighting & electrical", "median_cr": 2.8, "sigma": 0.8, "range": (0.3, 30.0),
             "discount": -0.06, "spread": 0.045, "share": 0.16, "titles": [
                 "Replacement of conventional street lights with LED fittings in {loc}",
                 "Shifting of overhead HT/LT lines underground along the main road, {loc}",
                 "Comprehensive annual maintenance of street lights in Ward {w}, {city}",
                 "Supply and erection of high-mast lighting at {n} junctions, {city}",
             ]},
    "WATER": {"label": "Water supply", "median_cr": 9.0, "sigma": 0.75, "range": (1.0, 120.0),
              "discount": -0.06, "spread": 0.045, "share": 0.12, "titles": [
                  "Laying of {d} mm DI water main from {loc} to {loc2}",
                  "Construction of {n} ML elevated service reservoir at {loc}",
                  "Replacement of old distribution network in {loc} (Package {ph})",
              ]},
    "BLDG": {"label": "Civic buildings", "median_cr": 8.0, "sigma": 0.7, "range": (1.0, 80.0),
             "discount": -0.07, "spread": 0.045, "share": 0.12, "titles": [
                 "Construction of ward office building at {loc}",
                 "Construction of municipal school building (G+{n}) at {loc}",
                 "Construction of urban primary health centre at {loc}",
                 "Renovation of civic hall and community centre at {loc}",
             ]},
}

DEPARTMENTS = {"ITS": ("Transport Engineering", "TE"), "ROADS": ("Public Works (Roads)", "RD"),
               "DRAIN": ("Storm Water Drainage", "SWD"), "ELEC": ("Electrical", "EL"),
               "WATER": ("Water Supply", "WS"), "BLDG": ("Buildings", "BD")}
SPV_MIX = {"ITS": 0.5, "ELEC": 0.2, "ROADS": 0.2, "BLDG": 0.1}

# region -> [(code, buyer name, weight, segment mix override or None, value multiplier)]
BUYERS: dict[str, list[tuple]] = {
    "MMR": [("NMMC", "Navi Mumbai Municipal Corporation", 0.28, None, 1.0),
            ("TMC", "Thane Municipal Corporation", 0.22, None, 1.0),
            ("CIDCO", "City and Industrial Development Corporation of Maharashtra", 0.16, None, 1.3),
            ("KDMC", "Kalyan-Dombivli Municipal Corporation", 0.14, None, 0.8),
            ("PNVMC", "Panvel Municipal Corporation", 0.08, None, 0.7),
            ("MMRDA", "Mumbai Metropolitan Region Development Authority", 0.12, {"ITS": 0.5, "ROADS": 0.5}, 2.0)],
    "PUNE": [("PMC", "Pune Municipal Corporation", 0.5, None, 1.0),
             ("PCMC", "Pimpri-Chinchwad Municipal Corporation", 0.35, None, 1.0),
             ("PSCDCL", "Pune Smart City Development Corporation Ltd", 0.15, SPV_MIX, 1.2)],
    "NASHIK": [("NMC", "Nashik Municipal Corporation", 0.75, None, 0.8),
               ("NMSCDCL", "Nashik Municipal Smart City Development Corporation Ltd", 0.25, SPV_MIX, 1.0)],
    "NAGPUR": [("NGPMC", "Nagpur Municipal Corporation", 0.75, None, 0.9),
               ("NSSCDCL", "Nagpur Smart and Sustainable City Development Corporation", 0.25, SPV_MIX, 1.1)],
    "GUJARAT": [("AMC", "Ahmedabad Municipal Corporation", 0.45, None, 1.1),
                ("SMC", "Surat Municipal Corporation", 0.35, None, 1.0),
                ("VMC", "Vadodara Municipal Corporation", 0.20, None, 0.8)],
    "CHENNAI": [("GCC", "Greater Chennai Corporation", 1.0, None, 1.0)],
    "HYDERABAD": [("GHMC", "Greater Hyderabad Municipal Corporation", 1.0, None, 1.0)],
    "BENGALURU": [("BBMP", "Bruhat Bengaluru Mahanagara Palike", 0.7, None, 1.0),
                  ("BSCL", "Bengaluru Smart City Ltd", 0.3, SPV_MIX, 1.2)],
}

# --- Names --------------------------------------------------------------------------

SURNAMES = {
    "west": ["Patil", "Deshpande", "Kulkarni", "Joshi", "Pawar", "Shinde", "Jadhav", "Gaikwad", "More", "Bhosale",
             "Sawant", "Naik", "Thakur", "Chavan", "Mane", "Salunkhe", "Kadam", "Wagh", "Bhagat", "Mhatre", "Gokhale",
             "Apte", "Ranade", "Kamble", "Londhe", "Phadke", "Karnik", "Dalvi", "Ghorpade", "Nimbalkar"],
    "gujarat": ["Shah", "Patel", "Mehta", "Desai", "Parikh", "Modi", "Trivedi", "Bhatt", "Vyas", "Pandya", "Dave",
                "Thakkar", "Chokshi", "Doshi", "Vora", "Soni"],
    "south": ["Iyer", "Reddy", "Rao", "Nair", "Pillai", "Krishnan", "Subramanian", "Naidu", "Menon", "Shetty",
              "Gowda", "Hegde", "Raghavan", "Venkataraman", "Chandrasekhar", "Murthy", "Prasad", "Varma", "Kumar",
              "Bhat"],
    "north": ["Sharma", "Gupta", "Agarwal", "Singh", "Verma", "Jain", "Malhotra", "Kapoor", "Chauhan", "Saxena",
              "Mishra", "Tiwari", "Yadav", "Bansal", "Goel", "Arora", "Khanna", "Sethi"],
    "other": ["Khan", "Qureshi", "Shaikh", "Ansari", "Siddiqui", "D'Souza", "Fernandes", "Pereira", "Irani", "Mistry"],
}
FIRST_NAMES = ["Amit", "Priya", "Sanjay", "Kavita", "Rahul", "Deepa", "Manoj", "Sunil", "Karan", "Pooja", "Nitin",
               "Lakshmi", "Harish", "Rekha", "Gaurav", "Swati", "Imran", "Divya", "Prakash", "Asha", "Vijay", "Anand",
               "Ramesh", "Suresh", "Mahesh", "Ashok", "Rajendra", "Vinod", "Madhuri", "Sneha", "Nilesh", "Sachin",
               "Aditya", "Rohan", "Vaibhav", "Ketan", "Hemant", "Jitendra", "Arvind", "Shalini", "Meenakshi",
               "Srinivas", "Venkat", "Ravi", "Kiran", "Farhan", "Salim", "Zubair", "Anjali", "Neha", "Tejas",
               "Mayur", "Chetan", "Bhavesh", "Hitesh", "Jignesh", "Parth", "Dhruv", "Yash", "Gopal", "Balaji",
               "Murali", "Karthik", "Arjun", "Naveen", "Pradeep", "Dinesh", "Sameer", "Uday", "Varun"]
MIDDLE_INITIALS = ["", "", "", "A.", "B.", "D.", "G.", "K.", "M.", "N.", "P.", "R.", "S.", "V."]

REGION_SURNAMES = {"MMR": ["west", "west", "north", "gujarat", "other"], "PUNE": ["west", "west", "west", "north"],
                   "NASHIK": ["west", "west", "west"], "NAGPUR": ["west", "west", "north"],
                   "GUJARAT": ["gujarat", "gujarat", "gujarat", "north"], "CHENNAI": ["south"],
                   "HYDERABAD": ["south", "south", "north"], "BENGALURU": ["south", "south", "north"],
                   "NCR": ["north", "north", "north", "other"]}
PLACE_WORDS = {"MMR": ["Konkan", "Sahyadri", "Thane Creek", "Arabian", "Parsik", "Western Coast"],
               "PUNE": ["Deccan Plateau", "Sinhagad", "Mula-Mutha", "Indrayani"],
               "NASHIK": ["Godavari Valley", "Panchavati", "Trimbak"], "NAGPUR": ["Vidarbha", "Satpura", "Wainganga"],
               "GUJARAT": ["Saurashtra", "Narmada", "Sabarmati", "Kutch"], "CHENNAI": ["Coromandel", "Marina", "Palar"],
               "HYDERABAD": ["Golconda", "Musi", "Krishna Valley"], "BENGALURU": ["Nandi", "Cauvery", "Garden City"],
               "NCR": ["Yamuna", "Aravali", "Capital"]}
AUSPICIOUS = ["Shree Ganesh", "Sai Samarth", "Siddhivinayak", "Balaji", "Mahalakshmi", "Shree Datta", "Om Sai",
              "Jay Ambe", "Hari Om", "Tirupati", "Gajanan", "Shree Renuka", "Jai Hanuman", "Swami Samarth",
              "Shree Krishna", "Umiya", "Khodiyar", "Ayyappa", "Murugan", "Venkateshwara"]
MODERN = ["Vertex", "Zenith", "Pinnacle", "Orbit", "Nexgen", "Infinity", "Crest", "Keystone", "Meridian", "Apollo",
          "Sterling", "Paramount", "Axis", "Summit", "Horizon", "Landmark", "Prism", "Radiant", "Unity", "Vanguard"]
SEGMENT_CORES = {
    "ITS": ["Traffic Systems", "Smart Mobility Solutions", "Signal Technologies", "Electronics & Controls",
            "Surveillance Systems", "Infotech", "Telematics", "Automation"],
    "ROADS": ["Constructions", "Infra Projects", "Road Builders", "Buildcon", "Infrastructure", "Roadways",
              "Engineering Works", "Highways"],
    "DRAIN": ["Civil Engineers", "Infra Works", "Hydro Structures", "Earthmovers", "Civil Contractors"],
    "ELEC": ["Electricals", "Power Solutions", "Electro Engineers", "Lighting Solutions", "Electrical Contractors",
             "Switchgears"],
    "WATER": ["Water Infrastructure", "Pipelines", "Hydraulic Engineers", "Aqua Projects", "Enviro Engineers"],
    "BLDG": ["Builders", "Developers", "Structures", "Construction Company", "Estates & Constructions"],
}
LEGAL_FORMS = {"large": [("Ltd.", "PUB"), ("Limited", "PUB"), ("Pvt. Ltd.", "PVT")],
               "medium": [("Pvt. Ltd.", "PVT"), ("Private Limited", "PVT"), ("Pvt Ltd", "PVT"), ("LLP", "LLP")],
               "small": [("Pvt. Ltd.", "PVT"), ("Pvt Ltd", "PVT"), ("LLP", "LLP"), ("& Co.", "FIRM"),
                         ("", "PROP")]}
CONSTITUTION = {"PUB": "Public Limited Company", "PVT": "Private Limited Company", "LLP": "Limited Liability Partnership",
                "FIRM": "Partnership Firm", "PROP": "Proprietorship"}
PAN_ENTITY = {"PUB": "C", "PVT": "C", "LLP": "F", "FIRM": "F", "PROP": "P"}
NIC_CODES = {"ITS": "74999", "ROADS": "42101", "DRAIN": "42201", "ELEC": "43210", "WATER": "42202", "BLDG": "41001"}
BUILDINGS = ["Siddhivinayak Chambers", "Shivam Business Centre", "Tirupati Plaza", "Sai Arcade", "Mahavir Trade Centre",
             "Om Heights", "Sapphire Business Park", "Krishna Complex", "Galaxy Towers", "Neelkanth Corporate Park",
             "Vardhman Chambers", "Ashirwad Commercial Complex", "Laxmi Industrial Estate", "Satyam Plaza",
             "Shreeji Arcade", "Crystal House", "Sunrise Business Hub", "Everest Chambers"]
ROADS = ["Station Road", "MG Road", "Link Road", "Ring Road", "Old Highway", "Market Road", "Industrial Area Road",
         "Main Road", "Temple Road", "Lake Road"]
UNREGISTERED_BIDDERS = ["Om Traders & Contractors", "Jai Bhavani Construction Co.", "R. K. Enterprises",
                        "New India Electrical Works", "Sai Kripa Earthmovers", "Metro Traffic Solutions",
                        "Sigma Signal Systems & Co.", "Bhagyalaxmi Civil Contractors", "S. N. Bhosale & Sons",
                        "Pragati Water Services"]

_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin(state_code: str, pan: str, entity_number: str = "1") -> str:
    """15-character GSTIN: state code + PAN + entity number + 'Z' + mod-36 check character."""
    base = f"{state_code}{pan}{entity_number}Z"
    total = 0
    for i, ch in enumerate(base):
        product = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return base + _GST_CHARS[(36 - total % 36) % 36]


def _region_meta(region: str) -> dict:
    return REGIONS.get(region) or NCR


def _person(rng: random.Random, region: str, used: set[tuple[str, str]]) -> tuple[str, str]:
    while True:
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(SURNAMES[rng.choice(REGION_SURNAMES[region])])
        if (first, last) not in used:
            used.add((first, last))
            middle = rng.choice(MIDDLE_INITIALS)
            return (f"{first} {middle} {last}" if middle else f"{first} {last}"), last


def _address(rng: random.Random, region: str) -> tuple[str, str]:
    meta = _region_meta(region)
    city, localities = rng.choice(meta["cities"])
    locality, pin = rng.choice(localities)
    style = rng.random()
    if city == "Navi Mumbai":
        head = f"Plot No. {rng.randint(1, 120)}, Sector {rng.randint(1, 50)}"
    elif "MIDC" in locality or "GIDC" in locality or style < 0.25:
        head = f"Plot No. {rng.choice('ABCDEFGW')}-{rng.randint(1, 180)}"
    elif style < 0.7:
        head = f"Office No. {rng.randint(101, 1204)}, {rng.choice(BUILDINGS)}, {rng.choice(ROADS)}"
    else:
        head = f"{rng.randint(1, 400)}, {rng.choice(ROADS)}"
    return f"{head}, {locality}, {city}, {meta['state']} {pin}", city


def _phone(rng: random.Random, city: str) -> str:
    std = {"Mumbai": "22", "Navi Mumbai": "22", "Thane": "22", "Kalyan": "251", "Panvel": "22", "Pune": "20",
           "Pimpri-Chinchwad": "20", "Nashik": "253", "Nagpur": "712", "Ahmedabad": "79", "Surat": "261",
           "Vadodara": "265", "Chennai": "44", "Hyderabad": "40", "Bengaluru": "80", "New Delhi": "11"}.get(city, "22")
    if rng.random() < 0.3:
        return f"+91 {rng.choice('6789')}{rng.randint(1000, 9999)} {rng.randint(10000, 99999)}"
    digits = 10 - len(std)
    local = str(rng.randint(10 ** (digits - 1) * 2, 10 ** digits - 1))
    return f"+91 {std} {local[:len(local) - 4]} {local[-4:]}"


def _slug(name: str) -> str:
    words = [w for w in name.replace("&", " ").replace(".", " ").split() if w.lower() not in
             ("pvt", "ltd", "private", "limited", "llp", "co", "shree", "the")]
    return "".join(w.lower() for w in words[:2] if w.isalpha()) or "firm"


def _email(rng: random.Random, name: str, tier: str) -> str:
    slug = _slug(name)
    if tier == "small" and rng.random() < 0.6:
        return f"{slug}{rng.choice(['', '.tenders', '123', '.infra'])}@{rng.choice(['gmail.com', 'yahoo.co.in', 'rediffmail.com'])}"
    return f"{rng.choice(['tenders', 'bids', 'info', 'contracts', 'projects'])}@{slug}.{rng.choice(['in', 'com', 'co.in'])}"


def _company_name(rng: random.Random, region: str, segment: str, founder_surname: str, tier: str) -> tuple[str, str]:
    core_word = rng.choice(SEGMENT_CORES[segment])
    style = rng.random()
    if style < 0.32:
        stem = founder_surname
    elif style < 0.55:
        stem = rng.choice(AUSPICIOUS)
    elif style < 0.72:
        stem = rng.choice(PLACE_WORDS[region])
    elif style < 0.85:
        stem = "".join(rng.choice("ABDGHJKMNPRSTV") for _ in range(rng.choice((2, 3))))
    else:
        stem = rng.choice(MODERN)
    suffix, form = rng.choice(LEGAL_FORMS[tier])
    if form == "PROP":
        core_word = rng.choice(["Enterprises", "Contractors", "Engineering Works", "Construction Co."])
    name = " ".join(p for p in (stem, core_word, suffix) if p)
    return name, form


def _profile(rng: random.Random, region: str, tier: str) -> dict:
    primary = rng.choices(list(SEGMENTS), weights=[s["share"] for s in SEGMENTS.values()])[0]
    # Civil contractors are usually generalists; systems and electrical firms specialise.
    companions = {"ROADS": ["DRAIN", "BLDG", "WATER"], "DRAIN": ["ROADS", "WATER", "BLDG"], "ELEC": ["ITS"],
                  "ITS": ["ELEC"], "WATER": ["DRAIN", "ROADS"], "BLDG": ["ROADS", "DRAIN"]}
    extra = rng.choices([0, 1, 2], weights=[0.35, 0.45, 0.2] if primary not in ("ITS", "ELEC") else [0.6, 0.4, 0])[0]
    segments = [primary] + rng.sample(companions[primary], min(extra, len(companions[primary])))
    turnover = {"small": rng.lognormvariate(1.3, 0.5), "medium": rng.lognormvariate(2.9, 0.4),
                "large": rng.lognormvariate(4.6, 0.5)}[tier]
    home = region if region in REGIONS else rng.choice(MARKET_REGIONS)
    neighbours = {"MMR": ["PUNE", "NASHIK"], "PUNE": ["MMR", "NASHIK"], "NASHIK": ["PUNE", "MMR"],
                  "NAGPUR": ["NASHIK"], "GUJARAT": ["MMR"], "CHENNAI": ["BENGALURU"], "HYDERABAD": ["BENGALURU"],
                  "BENGALURU": ["CHENNAI", "HYDERABAD"]}
    regions = [home]
    outstation = None
    if region == "NCR":
        regions = rng.sample(MARKET_REGIONS, rng.randint(3, 6))
    elif tier == "large":
        regions += rng.sample(neighbours[home], min(len(neighbours[home]), rng.randint(1, 2)))
        outstation = {"regions": [r for r in MARKET_REGIONS if r not in regions], "min_value_cr": 40}
    elif tier == "medium":
        if rng.random() < 0.4:
            regions.append(rng.choice(neighbours[home]))
        outstation = {"regions": [r for r in neighbours[home] if r not in regions], "min_value_cr": 8}
    elif rng.random() < 0.25:
        regions.append(rng.choice(neighbours[home]))
    return {
        "segments": segments, "home_region": region, "regions": regions, "outstation": outstation,
        "turnover_cr": round(turnover, 2),
        "propensity": round(rng.uniform(0.15, 0.42), 3),
        "price_bias": round(rng.gauss(0.0, 0.02), 4),
        "min_value_cr": 15 if tier == "large" else 0,
        "contractor_class": {"small": "Class III-IV", "medium": "Class I-II", "large": "Class I-A / Special"}[tier]
        + " (State PWD)",
    }


def build_registry(rng: random.Random) -> list[dict]:
    """Current bidders + hand-authored background actors + generated contractors."""
    vendors = [dict(v, source="registry", profile=BIDDER_PROFILES[v["vendor_id"]]) for v in BIDDERS]
    vendors += [dict(v, source="registry") for v in PLANTED_VENDORS]
    cores = [company_core(v["name"]) for v in vendors]
    used_people = {(d["name"].split()[0], d["name"].split()[-1]) for v in vendors for d in v["directors"]}
    used_dins = {d["din"] for v in vendors for d in v["directors"] if d.get("din")}
    used_pans = {v["pan"] for v in vendors}
    used_contacts = {x for v in vendors for x in (v["phone"], v["email"].split("@")[1], v["registered_address"])}
    regions = list(REGIONS) + ["NCR"]
    weights = [REGIONS[r]["vendor_share"] for r in REGIONS] + [NCR["vendor_share"]]

    idx = len(vendors) + 1
    while len(vendors) < N_REGISTERED_VENDORS:
        region = rng.choices(regions, weights=weights)[0]
        tier = "large" if region == "NCR" else rng.choices(["small", "medium", "large"], weights=[0.5, 0.36, 0.14])[0]
        profile = _profile(rng, region, tier)
        founder, surname = _person(rng, region, used_people)
        name, form = _company_name(rng, region if region in PLACE_WORDS else "NCR", profile["segments"][0], surname, tier)
        core = company_core(name)
        if any(fuzz.token_sort_ratio(core, c) >= 80 for c in cores):
            continue  # keep registry names unambiguous
        address, city = _address(rng, region)
        phone, email = _phone(rng, city), _email(rng, name, tier)
        domain = email.split("@")[1]
        if {address, phone, domain if not domain.startswith(("gmail", "yahoo", "rediff")) else email} & used_contacts:
            continue  # accidental collisions would read as planted relationships
        used_contacts.update((address, phone, domain))
        state = _region_meta(region)["state"]
        incorporated = date(rng.randint(1990 if tier == "large" else 2000, 2021), rng.randint(1, 12), rng.randint(1, 28))
        if form in ("PUB", "PVT"):
            cin = (f"{'L' if form == 'PUB' and rng.random() < 0.5 else 'U'}{NIC_CODES[profile['segments'][0]]}"
                   f"{STATE_ABBR[state]}{incorporated.year}{'PLC' if form == 'PUB' else 'PTC'}{rng.randint(100000, 399999)}")
        elif form == "LLP":
            cin = f"LLPIN AA{rng.choice('ABCDEFGHJK')}-{rng.randint(1000, 9999)}"
        else:
            cin = None
        people = [founder] + [_person(rng, region, used_people)[0] for _ in range(
            {"PUB": rng.randint(2, 4), "PVT": rng.randint(1, 2), "LLP": 1, "FIRM": rng.randint(1, 2), "PROP": 0}[form])]
        role = {"PUB": "Director", "PVT": "Director", "LLP": "Designated Partner", "FIRM": "Partner",
                "PROP": "Proprietor"}[form]
        directors = []
        for person in people:
            din = None
            if form in ("PUB", "PVT", "LLP"):  # partners and proprietors hold no DIN
                din = f"0{rng.randint(1000000, 9999999)}"
                while din in used_dins:
                    din = f"0{rng.randint(1000000, 9999999)}"
                used_dins.add(din)
            directors.append({"name": person, "din": din, "role": role})
        entity = PAN_ENTITY[form]
        first_letter = (surname if form == "PROP" else name)[0].upper()
        pan = f"{rng.choice('ABCDE')}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}" \
              f"{entity}{first_letter}{rng.randint(1000, 9999)}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}"
        if pan in used_pans:
            continue
        used_pans.add(pan)
        cores.append(core)
        vendors.append({
            "vendor_id": f"V{idx:03d}", "alias": None, "name": name, "pan": pan, "state_code": STATE_CODES[state],
            "registered_address": address, "phone": phone, "email": email,
            "incorporated": incorporated.isoformat(), "msme": tier == "small" or (tier == "medium" and rng.random() < 0.3),
            "directors": directors, "source": "registry",
            "profile": {"constitution": CONSTITUTION[form], "cin": cin, "tier": tier, **profile},
        })
        idx += 1
    return vendors


REGISTRY_FIELDS = ("constitution", "cin", "contractor_class", "home_region", "debarment")


def registry_meta(vendor: dict) -> dict:
    """What a vendor registry would actually hold - never the simulator's behavioural knobs."""
    profile = vendor["profile"]
    meta = {k: profile[k] for k in REGISTRY_FIELDS if profile.get(k)}
    meta["work_categories"] = [SEGMENTS[s]["label"] for s in profile["segments"]]
    meta["operating_regions"] = profile["regions"]
    return meta
