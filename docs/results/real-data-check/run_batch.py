"""Run every India 'Invitation for Bids' notice through the restructuring API; summarise results."""
import html, json, logging, os, re, sys, textwrap
from pathlib import Path
SCR = Path(sys.argv[1]); REPO = Path(sys.argv[2])
os.environ.update(TS_DATA_DIR=str(SCR / "real/batch"), TS_MARKET_DB=str(SCR / "real/market.db"),
                  TS_MARKET_COUNTRIES="India", TS_EXTRACTOR="pattern")
sys.path.insert(0, str(REPO / "backend")); logging.disable(logging.WARNING)
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from app.auth import create_user, issue_token
from app.db import fetch_one, init_db, session
from app.main import create_app

def notice_text(x):
    t = re.sub(r"<(br|p|tr|li|div|td|th)[^>]*>", "\n", x.get("notice_text") or "", flags=re.I)
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
    u = fetch_one(conn, "SELECT * FROM users WHERE email='batch@tendershield.localhost'") or create_user(conn, "batch@tendershield.localhost", "batch-runner-pw-123", "officer")
c = TestClient(create_app(), headers={"Authorization": "Bearer " + issue_token(u)[0]})
notices = [x for x in json.loads((REPO / "data/real/raw/worldbank/procurement_notices_india.json").read_text())["procnotices"] if x["notice_type"] == "Invitation for Bids"]
out = SCR / "real/batch_out"; out.mkdir(parents=True, exist_ok=True); rows = []
for x in notices:
    d = out / x["id"]; d.mkdir(exist_ok=True); text = notice_text(x)
    if len(text) < 200: rows.append({"id": x["id"], "status": "no text"}); continue
    (d / "notice.txt").write_text(text); to_pdf(text, d / "notice.pdf")
    r = c.post("/api/uploads/tender", files={"file": ("notice.pdf", (d / "notice.pdf").read_bytes(), "application/pdf")},
               data={"title": (x.get("bid_description") or x["project_name"])[:200], "department": x["project_name"][:120]})
    if r.status_code != 200: rows.append({"id": x["id"], "status": f"upload {r.status_code}"}); continue
    tid = r.json()["tender_id"]; r = c.post(f"/api/tenders/{tid}/restructure", json={})
    (d / "plan.json").write_text(r.text)
    if r.status_code != 200: rows.append({"id": x["id"], "status": f"restructure {r.status_code}"}); continue
    p = r.json(); rec = p["structures"]["scenarios"]["B_recommended"]
    rows.append({"id": x["id"], "tid": tid, "status": "ok", "group": x["procurement_group"], "title": x["bid_description"][:90].replace("\n", " "),
                 "project": x["project_name"][:50], "n_components": len(p["components"]),
                 "components": [f"{cc['label']} ({cc['n_items']}, {cc['mean_confidence']})" for cc in p["components"]],
                 "sources": sorted({i["source"] for cc in p["components"] for i in cc["items"]}),
                 "recommended_packages": rec["n_packages"], "splits": p["structures"]["recommendation_differs_from_current"],
                 "estimate": p["estimated_value_inr_cr"], "stays_best": p["structures"]["sensitivity"]["recommended_stays_best"]})
(out / "summary.json").write_text(json.dumps(rows, indent=1))
import collections
print(collections.Counter(r["status"] for r in rows))
ok = [r for r in rows if r["status"] == "ok"]
print("components hist", collections.Counter(r["n_components"] for r in ok), "splits", sum(r["splits"] for r in ok), "with estimate", sum(1 for r in ok if r["estimate"]))
for r in sorted(ok, key=lambda r: (-r["splits"], -r["n_components"]))[:25]:
    print(r["id"], r["group"], "split" if r["splits"] else "keep", r["recommended_packages"], r["estimate"], "|", r["title"][:70], "|", "; ".join(r["components"])[:200])
