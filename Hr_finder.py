"""
HR / recruiter contact finder, tuned for India (uses the Hunter.io API, not LinkedIn scraping).

Usage:
    python hr_finder.py tcs.com
    python hr_finder.py companies.txt            # one domain per line
    python hr_finder.py companies.txt --india-only   # keep only contacts with an India signal

Output: hr_contacts_india.csv
If HUNTER_API_KEY isn't set, the script asks you to paste it.
"""
import argparse
import csv
import os
import sys
import time

import requests

API = "https://api.hunter.io/v2/domain-search"
KEY = os.environ.get("HUNTER_API_KEY")

# Titles commonly used for hiring people at Indian companies
HR_WORDS = (
    "recruit", "talent", "hr ", "hr,", "human resources", "people", "hiring",
    "hrbp", "campus", "university relations", "early career", "staffing", "sourcer",
)
INDIA_DOMAIN_ENDINGS = (".in", ".co.in", ".org.in", ".net.in", ".ac.in")


def india_signal(row):
    """Hunter has no per-person country filter, so we use heuristics."""
    signals = []
    phone = (row["phone"] or "").replace(" ", "")
    if phone.startswith("+91") or phone.startswith("0091"):
        signals.append("phone +91")
    if row["domain"].lower().endswith(INDIA_DOMAIN_ENDINGS):
        signals.append("India domain")
    if "in.linkedin.com" in (row["linkedin"] or "").lower():
        signals.append("in.linkedin")
    return ", ".join(signals)


def find_hr(domain, limit=10):
    params = {"domain": domain, "department": "hr", "limit": limit, "api_key": KEY}
    r = requests.get(API, params=params, timeout=30)
    if r.status_code != 200:
        print(f"[!] {domain}: HTTP {r.status_code} {r.text[:150]}")
        return []
    data = r.json().get("data", {})
    rows = []
    for e in data.get("emails", []):
        position = (e.get("position") or "").lower() + " "
        row = {
            "company": data.get("organization") or domain,
            "domain": domain,
            "name": f"{e.get('first_name') or ''} {e.get('last_name') or ''}".strip(),
            "position": e.get("position") or "",
            "email": e.get("value") or "",
            "confidence": e.get("confidence") or 0,
            "phone": e.get("phone_number") or "",
            "linkedin": e.get("linkedin") or "",
            "verified": (e.get("verification") or {}).get("status") or "",
            "last_seen": max([x.get("last_seen_on") or "" for x in e.get("sources", [])] or [""]),
            "hr_title_match": any(w in position for w in HR_WORDS),
        }
        row["india_signal"] = india_signal(row)
        rows.append(row)
    # India signal first, then HR-titled, then confidence
    rows.sort(key=lambda x: (not x["india_signal"], not x["hr_title_match"], -x["confidence"]))
    return rows


def is_strict(r):
    """Verified mailbox, high confidence, and seen on the web within ~2 years."""
    recent = r["last_seen"] >= str(time.localtime().tm_year - 2)
    return r["verified"] == "valid" and r["confidence"] >= 90 and recent


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="a domain (tcs.com) or a text file with one domain per line")
    ap.add_argument("--strict", action="store_true", help="only verified, high-confidence, recently-seen contacts")
    ap.add_argument("--india-only", action="store_true", help="keep only contacts with an India signal")
    args = ap.parse_args()

    if not KEY:
        KEY = input("Paste your Hunter API key: ").strip()
    if not KEY:
        sys.exit("No API key given.")

    if os.path.isfile(args.target):
        domains = [l.strip() for l in open(args.target) if l.strip()]
    else:
        domains = [args.target]

    all_rows = []
    for d in domains:
        rows = find_hr(d)
        if args.strict:
            rows = [r for r in rows if is_strict(r)]
        if args.india_only:
            rows = [r for r in rows if r["india_signal"]]
        print(f"{d}: {len(rows)} contact(s)")
        all_rows.extend(rows)
        time.sleep(1)

    if not all_rows:
        print("Nothing found. Try without --india-only, or use the company's India domain (e.g. company.co.in).")
        return
    with open("hr_contacts_india.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        w.writeheader()
        w.writerows(all_rows)
    print(f"Saved {len(all_rows)} rows to hr_contacts_india.csv")


if __name__ == "__main__":
    main()