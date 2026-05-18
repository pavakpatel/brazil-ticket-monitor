from src.brazil_ticket_monitor.scrape import parse_fifa_rows, parse_money, parse_ticketmaster_body, parse_vivid_body, parse_seatgeek_body


def test_parse_money():
    assert parse_money("$1,181.67") == 1181.67
    assert parse_money("none") is None


def test_parse_fifa_rows_focus():
    rows = [
        ["Match", "Location", "Round", "Category", "Face Value", "Volume", "Last Sale", "Starting at"],
        ["M29\nBrazil vs. Haiti\nJune 19, 2026", "Philadelphia\nLincoln Financial Field", "Group C", "CAT1", "$445.00", "$113,466\n116 sales", "$1,099.00\n2 day ago", "$998.00"],
        [" M29 Brazil vs. Haiti June 19, 2026 ", "PhiladelphiaLincoln Financial Field", " Group C ", "CAT2", "$360.00", "$31,334\n35 sales", "$1,050.00\n2 day ago", "$1,150.00"],
    ]
    listings = parse_fifa_rows(rows)
    assert len(listings) == 2
    assert listings[0].match == "M29 Brazil vs. Haiti"
    assert listings[0].price == 998.0
    assert listings[1].category == "CAT2"


def test_parse_ticketmaster_body():
    body = """
    World Cup: Match 29 Group C - Brazil vs Haiti
    Fri • Jun 19, 2026 • 9:00 PM
    Lincoln Financial Field, Philadelphia, PA
    Sec 217 • Row 18
    Resale Ticket
    $1,181.67
    Mobile Entry
    Sec 211 • Row 9
    Resale Ticket
    $1,230.46
    Mobile Entry
    """
    parsed = parse_ticketmaster_body(body, "https://example.com/event")
    assert parsed["event_title"] == "World Cup: Match 29 Group C - Brazil vs Haiti"
    assert parsed["lowest_price"] == 1181.67
    assert parsed["listings"][0]["section_row"] == "Sec 217 • Row 18"



def test_parse_vivid_body():
    body = """
    Brazil vs Haiti - World Cup - Match 29 (Group C)
    Lincoln Financial Field in Philadelphia, PA
    Fri, Jun 19 at 9:00pm
    For fans who want to get in to see Brazil Mens National Football for the lowest price, tickets start at $879.
    The average ticket price for Brazil Mens National Football is $1,199.
    440 listings
    228
    Row 17 | 2 tickets
    Fees Incl.
    $879
    ea
    """
    parsed = parse_vivid_body(body, "https://example.com/vivid")
    assert parsed["lowest_price"] == 879.0
    assert parsed["average_price"] == 1199.0
    assert parsed["listing_count"] == 440
    assert parsed["cheapest_seen"]["section"] == "228"


def test_parse_seatgeek_blocked():
    parsed = parse_seatgeek_body("DataDome Device Check", "https://example.com/seatgeek")
    assert parsed["lowest_price"] is None
    assert "DataDome" in parsed["notes"][0]
