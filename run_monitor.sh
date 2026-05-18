#!/usr/bin/env bash
set -euo pipefail
cd /Users/fdddeveloper/brazil-ticket-monitor
python3 -m src.brazil_ticket_monitor.scrape --state /Users/fdddeveloper/brazil-ticket-monitor/data/state.json --out /Users/fdddeveloper/brazil-ticket-monitor/data/runs --mode full
