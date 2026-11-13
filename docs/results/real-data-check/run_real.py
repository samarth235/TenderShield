"""Run real World Bank India tender notices through the TenderShield API end-to-end."""
import html, json, os, re, sys, textwrap
from pathlib import Path

SCR = Path(sys.argv[1]); REPO = Path(sys.argv[2])
os.environ.update(TS_DATA_DIR=str(SCR / "real/run3"), TS_MARKET_DB=str(SCR / "real/market.db"),
                  TS_MARKET_COUNTRIES="India", TS_EXTRACTOR="pattern")
sys.path.insert(0, str(REPO / "backend"))
from fastapi.testclient import TestClient  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.auth import create_user, issue_token  # noqa: E402
from app.db import fetch_one, init_db, session  # noqa: E402
from app.main import create_app  # noqa: E402

notices = {x["id"]: x for x in json.loads((REPO / "data/real/raw/worldbank/procurement_notices_india.json").read_text())["procnotices"]}
OUT = SCR / "real/results3"

def notice_text(x):
    t = re.sub(r"<(br|p|tr|li|div)[^>]*>", "\n", x["notice_text"], flags=re.I)
    t = html.unescape(re.sub("<[^>]+>", " ", t))
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in t.splitlines() if l.strip())

def to_pdf(text, path):
    c = canvas.Canvas(str(path), pagesize=A4); y = 810
    for para in text.splitlines():
        for line in textwrap.wrap(para, 105) or [""]:
            if y < 40: c.showPage(); y = 810
            c.setFont("Helvetica", 8.5); c.drawString(30, y, line.encode("latin-1", "replace").decode("latin-1")); y -= 11
    c.save()

init_db()
with session() as conn:
    u = fetch_one(conn, "SELECT * FROM users WHERE email='runner@tendershield.localhost'") or \
        create_user(conn, "runner@tendershield.localhost", "real-data-runner-pw", "officer")
c = TestClient(create_app(), headers={"Authorization": "Bearer " + issue_token(u)[0]})
print("market:", {k: v for k, v in c.get("/api/market/status").json()["counts"].items()})

for nid in sys.argv[3:]:
    x = notices[nid]; d = OUT / nid; d.mkdir(parents=True, exist_ok=True)
    text = notice_text(x); (d / "notice.txt").write_text(text); to_pdf(text, d / "notice.pdf")
    r = c.post("/api/uploads/tender", files={"file": ("notice.pdf", (d / "notice.pdf").read_bytes(), "application/pdf")},
               data={"title": x["bid_description"][:200], "department": x["project_name"]})
    assert r.status_code == 200, r.text
    tid = r.json()["tender_id"]; (d / "upload.json").write_text(json.dumps(r.json(), indent=1, default=str))
    r = c.post(f"/api/tenders/{tid}/restructure", json={})
    (d / "plan.json").write_text(r.text)
    print(f"\n=== {nid} -> {tid}  restructure HTTP {r.status_code}")
    if r.status_code != 200: print(r.text[:400]); continue
    p = r.json(); rec = p["recommendation"]
    print("headline:", rec["headline"])
    print("estimate:", p["estimated_value_inr_cr"], p.get("estimate_source"))
    for comp in p["components"]:
        print(f"  comp {comp['label']:<42} items={comp['n_items']:<3} value={comp['value_inr_cr']} basis={comp['value_basis']} conf={comp['mean_confidence']}")
        for it in comp["items"][:2]: print("      -", it["text"][:110].replace("\n", " "), f"(p{it['page']}, {it['confidence']})")
    print("  unassigned:", len(p["unassigned_items"]))
    for e in p["dependency_graph"]["edges"]: print(f"  dep {e['source']}<->{e['target']} {e['strength']} {e['types']}")
    for k, s in p["structures"]["scenarios"].items():
        if s: print(f"  scenario {k}: score={s['score']} n={s['n_packages']} {s['summary'][:120]}")
    for pk in rec["packages"]: print("  pkg", {k: pk[k] for k in ("package", "scope", "value_inr_cr", "suppliers_with_full_capability_evidence", "of_which_meet_similar_work_scale", "sme_candidates", "expected_bidders_indicator")})
    print("  sensitivity:", p["structures"]["sensitivity"])
    print("  relationships: screened", p["relationships"]["screened_suppliers"], "review", p["relationships"]["requires_review"])
    for dq in p["data_quality"]: print("  dq", dq["level"], dq["issue"])
    r = c.post(f"/api/tenders/{tid}/restructuring/dossier"); print("  dossier", r.status_code, r.json().get("pages") if r.status_code == 200 else r.text[:200])
    if r.status_code == 200: (d / "dossier.pdf").write_bytes(c.get(r.json()["url"]).content)
