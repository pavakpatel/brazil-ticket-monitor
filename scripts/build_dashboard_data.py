#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
RUNS = DATA / 'runs'
OUT = DATA / 'dashboard.json'

def load(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def money(v):
    if v is None: return None
    try: return float(v)
    except Exception: return None

def summarize(snap):
    if not snap: return None
    focus = snap.get('focus', {}).get('fifa_collect_info', []) or []
    fifa = []
    for x in focus:
        fifa.append({
            'category': x.get('category',''),
            'starting_at': x.get('starting_at',''),
            'price': money(x.get('price')),
            'face_value': x.get('face_value',''),
        })
    tm = snap.get('ticketmaster') or {}
    first = (tm.get('listings') or [{}])[0]
    sg = snap.get('seatgeek') or {}
    vs = snap.get('vivid_seats') or {}
    return {
        'scraped_at_utc': snap.get('scraped_at_utc'),
        'fifa_haiti': fifa,
        'ticketmaster': {
            'lowest_price': money(tm.get('lowest_price')),
            'event_title': tm.get('event_title',''),
            'date': tm.get('date',''),
            'venue': tm.get('venue',''),
            'url': tm.get('url',''),
            'cheapest_seen': first,
        },
        'seatgeek': {
            'lowest_price': money(sg.get('lowest_price')),
            'event_title': sg.get('event_title',''),
            'url': sg.get('url',''),
            'notes': sg.get('notes', []),
        },
        'vivid_seats': {
            'lowest_price': money(vs.get('lowest_price')),
            'average_price': money(vs.get('average_price')),
            'listing_count': vs.get('listing_count'),
            'event_title': vs.get('event_title',''),
            'url': vs.get('url',''),
            'cheapest_seen': vs.get('cheapest_seen') or {},
            'notes': vs.get('notes', []),
        },
        'all_brazil_fifa': [
            {k: v for k, v in item.items() if k not in {'last_sale', 'details'}}
            for item in snap.get('all_brazil_fifa', [])
        ],
        'errors': snap.get('errors', []),
    }

def public_item(item):
    if not item:
        return None
    item = dict(item)
    item['fifa_haiti'] = [
        {k: v for k, v in dict(row).items() if k != 'last_sale'}
        for row in item.get('fifa_haiti', [])
    ]
    item['all_brazil_fifa'] = [
        {k: v for k, v in dict(row).items() if k not in {'last_sale', 'details'}}
        for row in item.get('all_brazil_fifa', [])
    ]
    return item

def merge_runs(existing, new):
    merged = {}
    for item in existing + new:
        item = public_item(item)
        if not item:
            continue
        key = item.get('scraped_at_utc') or item.get('file')
        if not key:
            continue
        merged[key] = item
    return sorted(
        merged.values(),
        key=lambda item: item.get('scraped_at_utc') or '',
    )[-50:]

existing = load(OUT) or {}
runs = []
for p in sorted(RUNS.glob('run-*.json')):
    s=load(p)
    item=summarize(s)
    if item:
        item['file']=str(p.relative_to(ROOT))
        runs.append(item)
current=public_item(summarize(load(DATA/'state.json'))) or public_item(existing.get('current'))
out={'current': current, 'runs': merge_runs(existing.get('runs', []), runs)}
OUT.write_text(json.dumps(out, indent=2), encoding='utf-8')
print(OUT)
