"""
Data access and tool functions (Step 3 of the build).

Each function fetches live data from Monday.com, normalizes it, and returns
(results, data_quality_notes). These are the functions that Claude calls
via tool use — they are the bridge between the LLM and the live data.

Important: All data comes from live API calls. Nothing is hardcoded.
"""

from datetime import datetime, date, timedelta
from config import get_config
from monday_client import fetch_all_items, get_board_columns, items_to_dicts
from normalize import normalize_deals, normalize_work_orders


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_and_normalize_deals() -> tuple[list[dict], list[str]]:
    """Fetch all deals from Monday.com and normalize them."""
    config = get_config()
    api_token = config["MONDAY_API_TOKEN"]
    board_id = config["DEALS_BOARD_ID"]

    if not api_token or not board_id:
        return [], ["ERROR: Monday.com API token or Deals board ID not configured."]

    try:
        columns = get_board_columns(board_id, api_token)
        raw_items = fetch_all_items(board_id, api_token)
        rows = items_to_dicts(raw_items, columns)
        return normalize_deals(rows)
    except Exception as e:
        return [], [f"ERROR fetching deals from Monday.com: {str(e)}"]


def _fetch_and_normalize_work_orders() -> tuple[list[dict], list[str]]:
    """Fetch all work orders from Monday.com and normalize them."""
    config = get_config()
    api_token = config["MONDAY_API_TOKEN"]
    board_id = config["WORK_ORDERS_BOARD_ID"]

    if not api_token or not board_id:
        return [], ["ERROR: Monday.com API token or Work Orders board ID not configured."]

    try:
        columns = get_board_columns(board_id, api_token)
        raw_items = fetch_all_items(board_id, api_token)
        rows = items_to_dicts(raw_items, columns)
        return normalize_work_orders(rows)
    except Exception as e:
        return [], [f"ERROR fetching work orders from Monday.com: {str(e)}"]


# ---------------------------------------------------------------------------
# Slim-down helpers (reduce token count for LLM context)
# ---------------------------------------------------------------------------

def _slim_deal(d: dict) -> dict:
    """Return only essential deal fields to minimize token usage."""
    return {
        "deal_name": d.get("deal_name", ""),
        "client_code": d.get("client_code", ""),
        "sector": d.get("sector", ""),
        "deal_stage": d.get("deal_stage", ""),
        "deal_status": d.get("deal_status", ""),
        "deal_value_display": d.get("deal_value_display", "N/A"),
        "closure_probability": d.get("closure_probability", "unrated"),
        "owner_code": d.get("owner_code", ""),
        "product_deal": d.get("product_deal", ""),
    }


def _slim_wo(w: dict) -> dict:
    """Return only essential work order fields to minimize token usage."""
    return {
        "deal_name": w.get("deal_name", ""),
        "serial_num": w.get("serial_num", ""),
        "sector": w.get("sector", ""),
        "execution_status": w.get("execution_status", ""),
        "amount_display": w.get("amount_display", "N/A"),
        "is_overdue": w.get("is_overdue", False),
        "billing_status": w.get("billing_status", ""),
        "wo_status": w.get("wo_status", ""),
    }


# ---------------------------------------------------------------------------
# Tool functions (called by the LLM via tool use)
# ---------------------------------------------------------------------------

def get_deals(
    sector: str | None = None,
    status: str | None = None,
    min_probability: str | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Fetch and filter deals from the Deals board.

    Args:
        sector: Filter by sector name (case-insensitive partial match).
                Example: "Mining", "Renewables", "Powerline"
        status: Filter by deal status. Values: "Open", "Won", "Dead", "On Hold"
        min_probability: Filter by minimum closure probability.
                         Values: "Low" (includes Low, Medium, High),
                                 "Medium" (includes Medium, High),
                                 "High" (only High)

    Returns:
        (filtered_deals, data_quality_notes)
    """
    all_deals, quality_notes = _fetch_and_normalize_deals()

    if not all_deals:
        return all_deals, quality_notes

    filtered = all_deals

    # Filter by sector
    if sector:
        sector_lower = sector.lower()
        filtered = [d for d in filtered if sector_lower in d["sector"].lower()]
        if not filtered:
            quality_notes.append(
                f"No deals found for sector '{sector}'. "
                f"Available sectors: {', '.join(sorted(set(d['sector'] for d in all_deals)))}"
            )

    # Filter by status
    if status:
        status_lower = status.lower()
        filtered = [d for d in filtered if d["deal_status"].lower() == status_lower]

    # Filter by minimum probability
    if min_probability:
        prob_hierarchy = {"low": 1, "medium": 2, "high": 3}
        min_level = prob_hierarchy.get(min_probability.lower(), 0)
        filtered = [
            d for d in filtered
            if prob_hierarchy.get(d["closure_probability"].lower(), 0) >= min_level
        ]

    # Add summary stats
    total_value = sum(d["deal_value"] for d in filtered if d["deal_value"] is not None)
    summary_note = (
        f"Returned {len(filtered)} deals"
        + (f" in sector '{sector}'" if sector else "")
        + (f" with status '{status}'" if status else "")
        + (f" with probability >= '{min_probability}'" if min_probability else "")
        + f". Total pipeline value: ₹{int(total_value):,}" if total_value else ""
    )
    quality_notes.insert(0, summary_note)

    return [_slim_deal(d) for d in filtered], quality_notes


def get_work_orders(
    sector: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Fetch and filter work orders from the Work Orders board.

    Args:
        sector: Filter by sector name (case-insensitive partial match).
                Example: "Mining", "Renewables", "Railways"
        status: Filter by execution status (case-insensitive partial match).
                Example: "Completed", "Ongoing", "Not Started", "Pause"

    Returns:
        (filtered_work_orders, data_quality_notes)
    """
    all_wo, quality_notes = _fetch_and_normalize_work_orders()

    if not all_wo:
        return all_wo, quality_notes

    filtered = all_wo

    # Filter by sector
    if sector:
        sector_lower = sector.lower()
        filtered = [w for w in filtered if sector_lower in w["sector"].lower()]
        if not filtered:
            quality_notes.append(
                f"No work orders found for sector '{sector}'. "
                f"Available sectors: {', '.join(sorted(set(w['sector'] for w in all_wo)))}"
            )

    # Filter by execution status
    if status:
        status_lower = status.lower()
        filtered = [w for w in filtered if status_lower in w["execution_status"].lower()]

    # Add summary
    total_value = sum(w["amount_excl_gst"] for w in filtered if w["amount_excl_gst"] is not None)
    overdue_count = sum(1 for w in filtered if w["is_overdue"])

    summary_note = (
        f"Returned {len(filtered)} work orders"
        + (f" in sector '{sector}'" if sector else "")
        + (f" with status containing '{status}'" if status else "")
        + f". Total contract value (excl GST): ₹{int(total_value):,}" if total_value else ""
    )
    quality_notes.insert(0, summary_note)

    if overdue_count > 0:
        quality_notes.append(f"{overdue_count} work order(s) appear to be overdue (past probable end date but not completed)")

    return [_slim_wo(w) for w in filtered], quality_notes


def get_cross_board_summary(
    sector: str | None = None,
) -> tuple[dict, list[str]]:
    """
    Attempt to join deals and work orders for a combined view.

    The join uses Deal Name matching (not customer codes, which use different
    naming schemes across the two boards: COMPANY_XXX vs WOCOMPANY_XXX).

    Args:
        sector: Optional sector filter (case-insensitive partial match).

    Returns:
        (summary_dict, data_quality_notes)
    """
    deals, deals_notes = _fetch_and_normalize_deals()
    work_orders, wo_notes = _fetch_and_normalize_work_orders()

    quality_notes = deals_notes + wo_notes

    # Check join key compatibility
    deal_client_codes = set(d["client_code"] for d in deals if d["client_code"])
    wo_customer_codes = set(w["customer_code"] for w in work_orders if w["customer_code"])

    code_overlap = deal_client_codes & wo_customer_codes
    if not code_overlap:
        quality_notes.append(
            "LIMITATION: Customer codes use different naming schemes across boards "
            f"(Deals: {sorted(deal_client_codes)[:3]}... vs Work Orders: {sorted(wo_customer_codes)[:3]}...). "
            "Cross-board matching is done by Deal Name instead, which is less reliable "
            "since multiple deals can share the same name."
        )

    # Apply sector filter
    if sector:
        sector_lower = sector.lower()
        deals = [d for d in deals if sector_lower in d["sector"].lower()]
        work_orders = [w for w in work_orders if sector_lower in w["sector"].lower()]

    # Match by deal name
    deal_names_with_wo = set()
    wo_by_name = {}
    for w in work_orders:
        name = w["deal_name"].lower()
        if name not in wo_by_name:
            wo_by_name[name] = []
        wo_by_name[name].append(w)

    matched_deals = []
    unmatched_deals = []
    for d in deals:
        name = d["deal_name"].lower()
        if name in wo_by_name:
            matched_deals.append({
                "deal": d,
                "work_orders": wo_by_name[name],
            })
            deal_names_with_wo.add(name)
        else:
            unmatched_deals.append(d)

    # Work orders not matched to any deal
    unmatched_wo = [
        w for w in work_orders if w["deal_name"].lower() not in {d["deal_name"].lower() for d in deals}
    ]

    # Slim down matched items to essential fields only
    slim_matched = []
    for m in matched_deals[:10]:
        slim_matched.append({
            "deal": _slim_deal(m["deal"]),
            "work_order_count": len(m["work_orders"]),
            "work_orders": [_slim_wo(w) for w in m["work_orders"][:3]],  # Max 3 WOs per deal
        })

    summary = {
        "matched_count": len(matched_deals),
        "unmatched_deals_count": len(unmatched_deals),
        "unmatched_work_orders_count": len(unmatched_wo),
        "matched_items": slim_matched,
        "sector_filter": sector,
        "total_deals": len(deals),
        "total_work_orders": len(work_orders),
    }

    quality_notes.append(
        f"Cross-board match: {len(matched_deals)} deals matched to work orders by name, "
        f"{len(unmatched_deals)} deals had no matching work order, "
        f"{len(unmatched_wo)} work orders had no matching deal."
    )

    return summary, quality_notes


def generate_leadership_summary(
    sector: str | None = None,
    quarter: str | None = None,
) -> tuple[dict, list[str]]:
    """
    Produce a structured summary suitable for a leadership update.

    This is the agent's interpretation of "help prepare data for leadership updates" —
    an on-demand structured summary rather than a scheduled report.

    Args:
        sector: Optional sector filter (case-insensitive partial match).
        quarter: Optional quarter filter. Format: "Q1 2026", "Q2 2025", etc.
                 If not specified, uses the current quarter.

    Returns:
        (summary_dict, data_quality_notes)
    """
    deals, deals_notes = _fetch_and_normalize_deals()
    work_orders, wo_notes = _fetch_and_normalize_work_orders()

    quality_notes = deals_notes + wo_notes

    # Parse quarter filter
    quarter_start = None
    quarter_end = None
    if quarter:
        match = __import__("re").match(r"Q(\d)\s*(\d{4})", quarter)
        if match:
            q = int(match.group(1))
            year = int(match.group(2))
            quarter_start = date(year, (q - 1) * 3 + 1, 1)
            if q == 4:
                quarter_end = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                quarter_end = date(year, q * 3 + 1, 1) - timedelta(days=1)
        else:
            quality_notes.append(f"Could not parse quarter '{quarter}'. Using all dates.")

    if not quarter_start:
        # Default to current quarter
        today = date.today()
        q = (today.month - 1) // 3 + 1
        quarter_start = date(today.year, (q - 1) * 3 + 1, 1)
        if q == 4:
            quarter_end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            quarter_end = date(today.year, q * 3 + 1, 1) - timedelta(days=1)
        quarter = f"Q{q} {today.year}"

    # Apply sector filter
    if sector:
        sector_lower = sector.lower()
        deals = [d for d in deals if sector_lower in d["sector"].lower()]
        work_orders = [w for w in work_orders if sector_lower in w["sector"].lower()]

    # --- Pipeline Overview ---
    open_deals = [d for d in deals if d["deal_status"].lower() == "open"]
    won_deals = [d for d in deals if d["deal_status"].lower() == "won"]
    dead_deals = [d for d in deals if d["deal_status"].lower() == "dead"]

    # Pipeline by sector
    pipeline_by_sector = {}
    for d in open_deals:
        s = d["sector"]
        if s not in pipeline_by_sector:
            pipeline_by_sector[s] = {"count": 0, "total_value": 0}
        pipeline_by_sector[s]["count"] += 1
        if d["deal_value"]:
            pipeline_by_sector[s]["total_value"] += d["deal_value"]

    # Pipeline by stage
    pipeline_by_stage = {}
    for d in open_deals:
        stage = d["deal_stage"] or "Unknown"
        if stage not in pipeline_by_stage:
            pipeline_by_stage[stage] = {"count": 0, "total_value": 0}
        pipeline_by_stage[stage]["count"] += 1
        if d["deal_value"]:
            pipeline_by_stage[stage]["total_value"] += d["deal_value"]

    # --- Stuck Deals (in same stage for > 30 days) ---
    stuck_deals = []
    today = date.today()
    for d in open_deals:
        if d["created_date"]:
            try:
                created = datetime.strptime(d["created_date"], "%Y-%m-%d").date()
                days_in_pipeline = (today - created).days
                if days_in_pipeline > 30:
                    stuck_deals.append({
                        "deal_name": d["deal_name"],
                        "sector": d["sector"],
                        "stage": d["deal_stage"],
                        "days_since_created": days_in_pipeline,
                        "value": d["deal_value"],
                        "probability": d["closure_probability"],
                    })
            except ValueError:
                pass

    stuck_deals.sort(key=lambda x: x["days_since_created"], reverse=True)

    # --- Stalled Work Orders (ongoing but past end date) ---
    stalled_wo = []
    for w in work_orders:
        if w["is_overdue"]:
            stalled_wo.append({
                "deal_name": w["deal_name"],
                "serial_num": w["serial_num"],
                "sector": w["sector"],
                "execution_status": w["execution_status"],
                "end_date": w["end_date"],
                "days_overdue": (today - datetime.strptime(w["end_date"], "%Y-%m-%d").date()).days if w["end_date"] else None,
                "amount": w["amount_excl_gst"],
            })

    stalled_wo.sort(key=lambda x: x.get("days_overdue") or 0, reverse=True)

    # --- Data Completeness ---
    total_deals = len(deals)
    prob_rated = sum(1 for d in deals if d["closure_probability"] != "unrated")
    has_value = sum(1 for d in deals if d["deal_value"] is not None)
    has_close_date = sum(1 for d in deals if d["tentative_close_date"])

    data_completeness = {
        "total_deals": total_deals,
        "with_probability_rating": f"{prob_rated}/{total_deals} ({100*prob_rated//max(total_deals,1)}%)",
        "with_deal_value": f"{has_value}/{total_deals} ({100*has_value//max(total_deals,1)}%)",
        "with_close_date": f"{has_close_date}/{total_deals} ({100*has_close_date//max(total_deals,1)}%)",
    }

    # --- Won deals this quarter ---
    won_this_quarter = []
    for d in won_deals:
        if d["close_date"]:
            try:
                close_dt = datetime.strptime(d["close_date"], "%Y-%m-%d").date()
                if quarter_start <= close_dt <= quarter_end:
                    won_this_quarter.append(d)
            except ValueError:
                pass

    won_value = sum(d["deal_value"] for d in won_this_quarter if d["deal_value"])

    # --- WO financial overview ---
    total_wo_value = sum(w["amount_excl_gst"] for w in work_orders if w["amount_excl_gst"])
    total_billed = sum(w["billed_excl_gst"] for w in work_orders if w["billed_excl_gst"])
    total_collected = sum(w["collected_amount"] for w in work_orders if w["collected_amount"])
    total_receivable = sum(w["receivable"] for w in work_orders if w["receivable"])

    summary = {
        "quarter": quarter,
        "sector_filter": sector,
        "pipeline_overview": {
            "total_open_deals": len(open_deals),
            "total_open_pipeline_value": sum(d["deal_value"] for d in open_deals if d["deal_value"]),
            "total_won_deals": len(won_deals),
            "total_dead_deals": len(dead_deals),
            "by_sector": {
                s: {"count": v["count"], "value": f"₹{int(v['total_value']):,}"}
                for s, v in sorted(pipeline_by_sector.items(), key=lambda x: x[1]["total_value"], reverse=True)
            },
            "by_stage": {
                s: {"count": v["count"], "value": f"₹{int(v['total_value']):,}"}
                for s, v in sorted(pipeline_by_stage.items(), key=lambda x: x[1]["total_value"], reverse=True)
            },
        },
        "won_this_quarter": {
            "count": len(won_this_quarter),
            "total_value": f"₹{int(won_value):,}" if won_value else "N/A",
            "deals": [
                {"name": d["deal_name"], "sector": d["sector"], "value": d["deal_value_display"]}
                for d in won_this_quarter[:10]
            ],
        },
        "stuck_deals": stuck_deals[:10],  # Top 10 longest-stuck
        "stalled_work_orders": stalled_wo[:10],  # Top 10 most overdue
        "work_order_financials": {
            "total_contract_value": f"₹{int(total_wo_value):,}" if total_wo_value else "N/A",
            "total_billed": f"₹{int(total_billed):,}" if total_billed else "N/A",
            "total_collected": f"₹{int(total_collected):,}" if total_collected else "N/A",
            "total_receivable": f"₹{int(total_receivable):,}" if total_receivable else "N/A",
        },
        "data_completeness": data_completeness,
    }

    return summary, quality_notes
