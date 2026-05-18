# Brazil World Cup Ticket Monitor

Browser-automation scraper for Brazil World Cup 2026 tickets, with special focus on Match 29: Brazil vs Haiti in Philadelphia.

Sources monitored:

- FIFA Collect Info Brazil listings: https://www.fifacollect.info/tickets/world-cup-2026/listings?team=brazil
- Ticketmaster event page for Brazil vs Haiti.
- SeatGeek event page for Brazil vs Haiti. Note: SeatGeek may block automated reads with DataDome; when it does, the run records `n/a` plus the source note rather than guessing.
- Vivid Seats event page for Brazil vs Haiti, including all-in lowest price, average price, listing count, and cheapest visible listing.

What it tracks:

- All Brazil games visible on FIFA Collect Info.
- Brazil vs Haiti lowest FIFA Collect prices by category.
- Ticketmaster Brazil vs Haiti event page, lowest resale price, and first visible listing details.
- SeatGeek availability/price when visible, or a clear block/no-price note when not visible.
- Vivid Seats all-in lowest price and listing count.
- Changes since the prior run: price movements, new/removed listings, source errors.

Run locally:

```bash
cd ~/brazil-ticket-monitor
python3 -m src.brazil_ticket_monitor.scrape --state data/state.json --out data/runs --mode full
```

Useful modes:

- `--mode full`: always print a concise update.
- `--mode changes`: print only when something changed or a source fails; ideal for quiet cron/watchdog use.

The scraper writes a timestamped JSON run artifact under `data/runs/` and persists comparison state in `data/state.json`.

Schedule:

A macOS LaunchAgent (`com.pavak.brazil-ticket-monitor`) runs this twice daily at 9 AM and 6 PM local time. It calls `/Users/fdddeveloper/.hermes/scripts/brazil_ticket_monitor.sh`, writes run artifacts, updates `data/dashboard.json`, and sends a local notification.
