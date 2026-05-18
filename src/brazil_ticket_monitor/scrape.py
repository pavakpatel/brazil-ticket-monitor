from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

FIFA_URL = "https://www.fifacollect.info/tickets/world-cup-2026/listings?team=brazil"
TM_SEARCH_URL = "https://www.ticketmaster.com/search?q=Brazil%20Haiti%20World%20Cup%202026"
TM_EVENT_URL_FALLBACK = "https://www.ticketmaster.com/event/Z7r9jZ1A743ff"
SEATGEEK_EVENT_URL = "https://seatgeek.com/fifa-world-cup-tickets/international-soccer/2026-06-19-9-pm/17213260"
VIVID_EVENT_URL = "https://www.vividseats.com/world-cup-soccer-tickets-lincoln-financial-field-6-19-2026--sports-soccer/production/5080479"
FOCUS_MATCH_RE = re.compile(r"brazil\s+vs\.?\s+haiti|haiti\s+vs\.?\s+brazil", re.I)
PRICE_RE = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)")


@dataclass
class Listing:
    source: str
    match: str
    date: str = ""
    location: str = ""
    round: str = ""
    category: str = ""
    face_value: str = ""
    volume: str = ""
    last_sale: str = ""
    starting_at: str = ""
    price: Optional[float] = None
    url: str = ""
    details: str = ""


def parse_money(text: str) -> Optional[float]:
    m = PRICE_RE.search(text or "")
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def parse_fifa_rows(rows: List[List[str]], url: str = FIFA_URL) -> List[Listing]:
    listings: List[Listing] = []
    current_match = ""
    current_date = ""
    for row in rows:
        if len(row) < 8 or row[0].strip().lower() == "match":
            continue
        match_cell = clean(row[0])
        if match_cell:
            # Examples: "M29 Brazil vs. Haiti June 19, 2026" or continuation rows with the same text.
            match_match = re.search(r"(M\d+\s+.+?)(?:\s+June|\s+July|\s+May|\s+June|$)", match_cell)
            date_match = re.search(r"((?:May|June|July) \d{1,2}, 2026)", match_cell)
            if match_match:
                current_match = clean(match_match.group(1))
            if date_match:
                current_date = date_match.group(1)
        if not current_match:
            continue
        listing = Listing(
            source="fifa_collect_info",
            match=current_match,
            date=current_date,
            location=clean(row[1]) if len(row) > 1 else "",
            round=clean(row[2]) if len(row) > 2 else "",
            category=clean(row[3]) if len(row) > 3 else "",
            face_value=clean(row[4]) if len(row) > 4 else "",
            volume=clean(row[5]) if len(row) > 5 else "",
            last_sale=clean(row[6]) if len(row) > 6 else "",
            starting_at=clean(row[7]) if len(row) > 7 else "",
            price=parse_money(row[7] if len(row) > 7 else ""),
            url=url,
            details=clean(row[9]) if len(row) > 9 else "",
        )
        listings.append(listing)
    return listings


def parse_ticketmaster_body(body: str, url: str) -> Dict[str, Any]:
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    result: Dict[str, Any] = {
        "source": "ticketmaster",
        "url": url,
        "event_title": "",
        "date": "",
        "venue": "",
        "lowest_price": None,
        "listings": [],
        "notes": [],
    }
    for i, line in enumerate(lines):
        if "Brazil vs Haiti" in line or "Brazil vs. Haiti" in line:
            result["event_title"] = line
            break
    for line in lines:
        if "Jun 19, 2026" in line or "6/19/26" in line:
            result["date"] = line
            break
    for line in lines:
        if "Lincoln Financial Field" in line:
            result["venue"] = line
            break
    for i, line in enumerate(lines):
        if line.startswith("Sec ") and i + 2 < len(lines):
            window = lines[i : min(i + 5, len(lines))]
            price_line = next((x for x in window if PRICE_RE.search(x)), "")
            if price_line:
                result["listings"].append(
                    {
                        "section_row": line,
                        "type": next((x for x in window if "Ticket" in x), ""),
                        "price": parse_money(price_line),
                        "price_text": price_line,
                    }
                )
    prices = [x["price"] for x in result["listings"] if x.get("price") is not None]
    if prices:
        result["lowest_price"] = min(prices)
    if "Tickets are sold out" in body or "No tickets available" in body:
        result["notes"].append("Ticketmaster says no tickets are currently available.")
    return result


def parse_vivid_body(body: str, url: str) -> Dict[str, Any]:
    """Parse Vivid Seats' rendered event page text.

    Vivid is a nice add because it exposes all-in prices and a deal score in the
    rendered page, so we can track it without treating random dollar amounts as
    authoritative.
    """
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    result: Dict[str, Any] = {
        "source": "vivid_seats",
        "url": url,
        "event_title": "",
        "date": "",
        "venue": "",
        "lowest_price": None,
        "average_price": None,
        "listing_count": None,
        "cheapest_seen": {},
        "listings": [],
        "notes": [],
    }
    for line in lines:
        if "Brazil vs Haiti" in line or "Brazil vs. Haiti" in line:
            result["event_title"] = line
            break
    for line in lines:
        if "Fri, Jun 19" in line or "Jun 19" in line:
            result["date"] = line
            break
    for line in lines:
        if "Lincoln Financial Field" in line:
            result["venue"] = line
            break
    m = re.search(r"tickets start at\s+\$([0-9,]+(?:\.[0-9]{2})?)", body or "", re.I)
    if m:
        result["lowest_price"] = float(m.group(1).replace(",", ""))
    m = re.search(r"average ticket price.*?\$([0-9,]+(?:\.[0-9]{2})?)", body or "", re.I | re.S)
    if m:
        result["average_price"] = float(m.group(1).replace(",", ""))
    m = re.search(r"(\d[\d,]*)\s+listings", body or "", re.I)
    if m:
        result["listing_count"] = int(m.group(1).replace(",", ""))
    # Rendered listing blocks look like: section, row, optional labels, price, ea.
    for i, line in enumerate(lines):
        if re.fullmatch(r"[A-Z]?\d{1,3}", line) and i + 2 < len(lines):
            window = lines[i : min(i + 10, len(lines))]
            price_line = next((x for x in window if PRICE_RE.fullmatch(x)), "")
            row_line = next((x for x in window if x.lower().startswith("row ")), "")
            price = parse_money(price_line)
            if price is not None:
                result["listings"].append({"section": line, "row": row_line, "price": price, "price_text": price_line})
    if result["listings"]:
        result["listings"] = sorted(result["listings"], key=lambda x: x.get("price") or 10**9)[:10]
        result["cheapest_seen"] = result["listings"][0]
        if result["lowest_price"] is None:
            result["lowest_price"] = result["cheapest_seen"].get("price")
    if not result["lowest_price"]:
        result["notes"].append("Vivid loaded, but no validated lowest price was found.")
    return result


def parse_seatgeek_body(body: str, url: str) -> Dict[str, Any]:
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    result: Dict[str, Any] = {
        "source": "seatgeek",
        "url": url,
        "event_title": "Brazil vs Haiti - World Cup",
        "lowest_price": None,
        "listings": [],
        "notes": [],
    }
    if "DataDome" in (body or "") or "Device Check" in (body or ""):
        result["notes"].append("SeatGeek blocked automated access with DataDome; source is tracked but price not captured this run.")
        return result
    for line in lines:
        if "Brazil" in line and "Haiti" in line:
            result["event_title"] = line
            break
    prices = [parse_money(x) for x in lines if PRICE_RE.search(x)]
    prices = [x for x in prices if x is not None and 50 <= x <= 10000]
    if prices:
        result["lowest_price"] = min(prices)
    else:
        result["notes"].append("SeatGeek page loaded, but no validated visible price was found.")
    return result


def snapshot_key(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    fifa_focus = snapshot.get("focus", {}).get("fifa_collect_info", [])
    tm = snapshot.get("ticketmaster", {})
    return {
        "fifa_focus": [
            {
                "match": x.get("match"),
                "category": x.get("category"),
                "starting_at": x.get("starting_at"),
                "last_sale": x.get("last_sale"),
            }
            for x in fifa_focus
        ],
        "ticketmaster_lowest_price": tm.get("lowest_price"),
        "ticketmaster_first_listings": tm.get("listings", [])[:5],
        "seatgeek_lowest_price": snapshot.get("seatgeek", {}).get("lowest_price"),
        "vivid_lowest_price": snapshot.get("vivid_seats", {}).get("lowest_price"),
        "errors": snapshot.get("errors", []),
    }


def compare(prev: Optional[Dict[str, Any]], curr: Dict[str, Any]) -> List[str]:
    if not prev:
        return ["Initial baseline captured."]
    changes: List[str] = []
    prev_key = snapshot_key(prev)
    curr_key = snapshot_key(curr)
    if curr.get("errors"):
        changes.append("One or more sources had errors: " + "; ".join(curr.get("errors", [])))
    # FIFA category-level movements.
    prev_fifa = {(x.get("match"), x.get("category")): x for x in prev_key.get("fifa_focus", [])}
    curr_fifa = {(x.get("match"), x.get("category")): x for x in curr_key.get("fifa_focus", [])}
    for key, curr_item in curr_fifa.items():
        prev_item = prev_fifa.get(key)
        if not prev_item:
            changes.append(f"FIFA Collect added {key[0]} {key[1]} at {curr_item.get('starting_at')}.")
        elif curr_item.get("starting_at") != prev_item.get("starting_at"):
            changes.append(
                f"FIFA Collect {key[0]} {key[1]} moved from {prev_item.get('starting_at')} to {curr_item.get('starting_at')}.")
    for key in prev_fifa.keys() - curr_fifa.keys():
        changes.append(f"FIFA Collect removed/hidden {key[0]} {key[1]}.")
    # Ticketmaster lowest movement.
    if curr_key.get("ticketmaster_lowest_price") != prev_key.get("ticketmaster_lowest_price"):
        changes.append(
            f"Ticketmaster lowest moved from {fmt_price(prev_key.get('ticketmaster_lowest_price'))} to {fmt_price(curr_key.get('ticketmaster_lowest_price'))}.")
    if curr_key.get("seatgeek_lowest_price") != prev_key.get("seatgeek_lowest_price"):
        changes.append(
            f"SeatGeek lowest moved from {fmt_price(prev_key.get('seatgeek_lowest_price'))} to {fmt_price(curr_key.get('seatgeek_lowest_price'))}.")
    if curr_key.get("vivid_lowest_price") != prev_key.get("vivid_lowest_price"):
        changes.append(
            f"Vivid Seats lowest moved from {fmt_price(prev_key.get('vivid_lowest_price'))} to {fmt_price(curr_key.get('vivid_lowest_price'))}.")
    return changes


def fmt_price(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def scrape(headless: bool = True) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot: Dict[str, Any] = {
        "scraped_at_utc": now,
        "sources": {"fifa_collect_info": FIFA_URL, "ticketmaster_search": TM_SEARCH_URL, "seatgeek_event": SEATGEEK_EVENT_URL, "vivid_seats_event": VIVID_EVENT_URL},
        "all_brazil_fifa": [],
        "focus": {"fifa_collect_info": []},
        "ticketmaster": {},
        "seatgeek": {},
        "vivid_seats": {},
        "errors": [],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        try:
            page.goto(FIFA_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2500)
            rows = page.evaluate("Array.from(document.querySelectorAll('table tr')).map(tr=>Array.from(tr.cells||[]).map(td=>td.innerText))")
            fifa = [asdict(x) for x in parse_fifa_rows(rows)]
            snapshot["all_brazil_fifa"] = fifa
            snapshot["focus"]["fifa_collect_info"] = [x for x in fifa if FOCUS_MATCH_RE.search(x.get("match", ""))]
        except Exception as e:
            snapshot["errors"].append(f"FIFA Collect scrape failed: {type(e).__name__}: {e}")
        try:
            page.goto(TM_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            event_url = page.evaluate(
                """() => {
                    const links = Array.from(document.querySelectorAll('a'));
                    const hit = links.find(a => /Brazil\s+vs\.?\s+Haiti/i.test(a.innerText || '') && /event\//.test(a.href));
                    return hit ? hit.href : '';
                }"""
            ) or TM_EVENT_URL_FALLBACK
            snapshot["sources"]["ticketmaster_event"] = event_url
            page.goto(event_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)
            # Accept info modal/cookies if present; failures are harmless.
            for label in ["Accept & Continue", "Accept All", "Dismiss popup"]:
                try:
                    page.get_by_text(label, exact=True).click(timeout=1000)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
            body = page.evaluate("document.body.innerText")
            snapshot["ticketmaster"] = parse_ticketmaster_body(body, page.url)
        except Exception as e:
            snapshot["errors"].append(f"Ticketmaster scrape failed: {type(e).__name__}: {e}")
        try:
            page.goto(SEATGEEK_EVENT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            body = page.evaluate("document.body.innerText")
            snapshot["seatgeek"] = parse_seatgeek_body(body, page.url)
        except Exception as e:
            snapshot["errors"].append(f"SeatGeek scrape failed: {type(e).__name__}: {e}")
            snapshot["seatgeek"] = {"source": "seatgeek", "url": SEATGEEK_EVENT_URL, "lowest_price": None, "notes": [f"SeatGeek scrape failed: {type(e).__name__}: {e}"]}
        try:
            page.goto(VIVID_EVENT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)
            body = page.evaluate("document.body.innerText")
            snapshot["vivid_seats"] = parse_vivid_body(body, page.url)
        except Exception as e:
            snapshot["errors"].append(f"Vivid Seats scrape failed: {type(e).__name__}: {e}")
        context.close()
        browser.close()
    return snapshot


def render(snapshot: Dict[str, Any], changes: List[str], mode: str) -> str:
    focus = snapshot.get("focus", {}).get("fifa_collect_info", [])
    tm = snapshot.get("ticketmaster", {})
    if mode == "changes" and not changes:
        return ""
    lines = []
    lines.append("Brazil ticket watch update ⚽🇧🇷")
    lines.append(f"Checked: {snapshot.get('scraped_at_utc')} UTC")
    if focus:
        lines.append("Brazil vs Haiti — FIFA Collect:")
        for item in focus:
            lines.append(
                f"- {item.get('category')}: starting {item.get('starting_at') or 'n/a'}; last sale {item.get('last_sale') or 'n/a'}; face {item.get('face_value') or 'n/a'}"
            )
    else:
        lines.append("Brazil vs Haiti — FIFA Collect: no rows found.")
    if tm:
        listings = tm.get("listings", [])
        first = listings[0] if listings else {}
        lines.append(f"Ticketmaster: lowest visible resale {fmt_price(tm.get('lowest_price'))}.")
        if first:
            lines.append(f"- Cheapest seen: {first.get('section_row')} at {first.get('price_text')}")
        if tm.get("url"):
            lines.append(f"- Event: {tm.get('url')}")
    else:
        lines.append("Ticketmaster: no event data captured.")
    sg = snapshot.get("seatgeek") or {}
    if sg:
        lines.append(f"SeatGeek: lowest visible {fmt_price(sg.get('lowest_price'))}.")
        for note in sg.get("notes", [])[:2]:
            lines.append(f"- SeatGeek note: {note}")
        if sg.get("url"):
            lines.append(f"- Event: {sg.get('url')}")
    vs = snapshot.get("vivid_seats") or {}
    if vs:
        extra = []
        if vs.get("average_price") is not None:
            extra.append(f"avg {fmt_price(vs.get('average_price'))}")
        if vs.get("listing_count") is not None:
            extra.append(f"{vs.get('listing_count')} listings")
        suffix = f" ({'; '.join(extra)})" if extra else ""
        lines.append(f"Vivid Seats: lowest all-in {fmt_price(vs.get('lowest_price'))}{suffix}.")
        cheapest = vs.get("cheapest_seen") or {}
        if cheapest:
            lines.append(f"- Cheapest seen: Section {cheapest.get('section')} {cheapest.get('row')} at {cheapest.get('price_text')}")
        if vs.get("url"):
            lines.append(f"- Event: {vs.get('url')}")
    all_games = snapshot.get("all_brazil_fifa", [])
    if all_games:
        by_match: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for item in all_games:
            key = (item.get("match", ""), item.get("date", ""))
            current = by_match.get(key)
            if current is None or (item.get("price") is not None and (current.get("price") is None or item.get("price") < current.get("price"))):
                by_match[key] = item
        lines.append("All Brazil FIFA Collect games tracked:")
        for item in by_match.values():
            lines.append(
                f"- {item.get('match')} — {item.get('date')} — {item.get('location')} — cheapest seen {item.get('category')} {item.get('starting_at') or 'n/a'}"
            )
    if changes:
        lines.append("Changes since last run:")
        for change in changes:
            lines.append(f"- {change}")
    else:
        lines.append("Changes since last run: none.")
    if snapshot.get("errors"):
        lines.append("Source issues:")
        for err in snapshot["errors"]:
            lines.append(f"- {err}")
    lines.append("Move fast if FIFA CAT1 drops near face value or Ticketmaster dips below FIFA Collect — that’s the good-text-her-now moment.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=str(Path.home() / "brazil-ticket-monitor" / "data" / "state.json"))
    parser.add_argument("--out", default=str(Path.home() / "brazil-ticket-monitor" / "data" / "runs"))
    parser.add_argument("--mode", choices=["full", "changes"], default="full")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    state_path = Path(os.path.expanduser(args.state))
    out_dir = Path(os.path.expanduser(args.out))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    prev = None
    if state_path.exists():
        try:
            prev = json.loads(state_path.read_text())
        except Exception:
            prev = None
    snapshot = scrape(headless=not args.headed)
    changes = compare(prev, snapshot)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"run-{stamp}.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    state_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    output = render(snapshot, changes, args.mode)
    if output:
        print(output)
    return 2 if snapshot.get("errors") and not snapshot.get("focus", {}).get("fifa_collect_info") and not snapshot.get("ticketmaster") else 0


if __name__ == "__main__":
    raise SystemExit(main())
