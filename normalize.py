"""
Data normalization layer (Step 2 of the build).

Transforms raw Monday.com board data into clean, structured dictionaries.
Handles known data quirks from both boards and generates plain-English
data quality notes that get surfaced to the end user.

Key design decisions:
- Column matching is done by title (case-insensitive partial match) since
  Monday.com assigns random column IDs on import.
- Blank/null values are never silently defaulted — they're explicitly marked
  and counted in quality notes.
- Embedded header rows (a known quirk of the source CSV) are detected and skipped.
"""

import re
from datetime import datetime, date


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _parse_float(val: str) -> float | None:
    """Parse a string to float, handling common issues."""
    if not val or not val.strip():
        return None
    cleaned = val.strip().replace(",", "").replace("₹", "").replace(" ", "")
    # Handle #VALUE! errors from Excel
    if cleaned.startswith("#") or cleaned.lower() in ("n/a", "na", "-", ""):
        return None
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_date(val: str) -> str | None:
    """
    Parse a date string to ISO format (YYYY-MM-DD).
    Handles multiple formats: YYYY-MM-DD, DD-MM-YYYY, MM/DD/YYYY, etc.
    Returns None for blank/unparseable values.
    """
    if not val or not val.strip():
        return None

    val = val.strip()

    # Already ISO format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        return val

    # Try common formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _find_column_value(row: dict, *search_terms: str) -> str:
    """
    Find a column value by searching for partial matches in column titles.
    Tries each search term in order (case-insensitive).
    Returns the first non-empty match, or empty string if nothing found.
    """
    for term in search_terms:
        term_lower = term.lower()
        for key, val in row.items():
            if key.startswith("_"):
                continue
            if term_lower in key.lower():
                return val or ""
    return ""


def _is_header_row(row: dict) -> bool:
    """
    Detect rows that contain column headers re-embedded as data.
    These are a known quirk of the source CSV files.
    """
    # Check if multiple values look like column names
    header_indicators = [
        "Deal Status", "Close Date", "Closure Probability",
        "Tentative Close Date", "Deal Stage", "Product deal",
        "Sector/service", "Created Date"
    ]
    values = [str(v) for k, v in row.items() if not k.startswith("_")]
    matches = sum(1 for indicator in header_indicators if indicator in values)
    return matches >= 3


# ---------------------------------------------------------------------------
# Deals normalization
# ---------------------------------------------------------------------------

# Deal stage ordering (the letter prefix encodes funnel order)
DEAL_STAGE_ORDER = {
    "A": 1,   # Lead Generated
    "B": 2,   # Sales Qualified Leads
    "C": 3,   # Demo Done
    "D": 4,   # Feasibility
    "E": 5,   # Proposal/Commercials Sent
    "F": 6,   # Negotiations
    "G": 7,   # Project Won
    "H": 8,   # Work Order Received
    "I": 9,   # POC
    "J": 10,  # Invoice sent
    "K": 11,  # Amount Accrued
    "L": 12,  # Project Lost
    "M": 13,  # Projects On Hold
    "N": 14,  # Not relevant at the moment
    "O": 15,  # Not Relevant at all
}


def _get_stage_order(stage: str) -> int:
    """Extract the numeric order from a deal stage's letter prefix."""
    if not stage:
        return 99
    match = re.match(r"^([A-O])\.", stage)
    if match:
        return DEAL_STAGE_ORDER.get(match.group(1), 99)
    # Handle "Project Completed" which has no letter prefix
    if "completed" in stage.lower():
        return 16
    return 99


def normalize_deals(raw_rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Normalize raw Deals board data.

    Args:
        raw_rows: List of dicts from items_to_dicts() (column title -> text value)

    Returns:
        (clean_items, data_quality_notes)
    """
    clean_items = []
    quality_notes = []

    # Counters for data quality tracking
    total = 0
    header_rows_skipped = 0
    missing_probability = 0
    missing_deal_value = 0
    missing_sector = 0
    missing_deal_name = 0
    missing_owner = 0
    missing_stage = 0
    missing_created_date = 0

    for row in raw_rows:
        # Skip embedded header rows
        if _is_header_row(row):
            header_rows_skipped += 1
            continue

        total += 1

        # Extract values by searching column titles (handles Monday.com renaming)
        deal_name = row.get("_item_name", "") or ""
        owner_code = _find_column_value(row, "Owner code", "Owner")
        client_code = _find_column_value(row, "Client Code", "Client")
        deal_status = _find_column_value(row, "Deal Status", "Status")
        close_date_str = _find_column_value(row, "Close Date")
        closure_prob = _find_column_value(row, "Closure Probability", "Probability")
        deal_value_str = _find_column_value(row, "Masked Deal value", "Deal value")
        tentative_close_str = _find_column_value(row, "Tentative Close Date", "Tentative Close")
        deal_stage = _find_column_value(row, "Deal Stage", "Stage")
        product_deal = _find_column_value(row, "Product deal", "Product")
        sector = _find_column_value(row, "Sector/service", "Sector")
        created_date_str = _find_column_value(row, "Created Date", "Created")

        # Parse and clean
        deal_value = _parse_float(deal_value_str)
        close_date = _parse_date(close_date_str)
        tentative_close = _parse_date(tentative_close_str)
        created_date = _parse_date(created_date_str)

        # Normalize closure probability — never silently default to Medium
        if not closure_prob or closure_prob.strip() == "":
            closure_prob = "unrated"
        else:
            closure_prob = closure_prob.strip().capitalize()
            if closure_prob not in ("High", "Medium", "Low"):
                closure_prob = "unrated"

        # Normalize deal status
        if not deal_status or deal_status.strip() == "":
            deal_status = "Unknown"
        else:
            deal_status = deal_status.strip()

        # Normalize sector
        if not sector or sector.strip() == "":
            sector = "Unspecified"
        else:
            sector = sector.strip()

        # Track quality issues
        if closure_prob == "unrated":
            missing_probability += 1
        if deal_value is None:
            missing_deal_value += 1
        if sector == "Unspecified":
            missing_sector += 1
        if not deal_name.strip():
            missing_deal_name += 1
            deal_name = f"Unnamed Deal (row {total})"
        if not owner_code.strip():
            missing_owner += 1
        if not deal_stage.strip():
            missing_stage += 1
        if created_date is None:
            missing_created_date += 1

        clean_items.append({
            "deal_name": deal_name.strip(),
            "owner_code": owner_code.strip(),
            "client_code": client_code.strip(),
            "deal_status": deal_status,
            "close_date": close_date,
            "closure_probability": closure_prob,
            "deal_value": deal_value,
            "deal_value_display": f"₹{int(deal_value):,}" if deal_value else "N/A",
            "tentative_close_date": tentative_close,
            "deal_stage": deal_stage.strip(),
            "deal_stage_order": _get_stage_order(deal_stage.strip()),
            "product_deal": product_deal.strip(),
            "sector": sector,
            "created_date": created_date,
        })

    # Build quality notes
    if header_rows_skipped > 0:
        quality_notes.append(
            f"{header_rows_skipped} embedded header row(s) were detected and skipped from the data"
        )
    if missing_probability > 0:
        quality_notes.append(
            f"{missing_probability} of {total} deals had no Closure Probability rating (marked as 'unrated')"
        )
    if missing_deal_value > 0:
        quality_notes.append(
            f"{missing_deal_value} of {total} deals had no deal value recorded"
        )
    if missing_sector > 0:
        quality_notes.append(
            f"{missing_sector} of {total} deals had no sector specified"
        )
    if missing_deal_name > 0:
        quality_notes.append(
            f"{missing_deal_name} deal(s) had no name"
        )
    if missing_owner > 0:
        quality_notes.append(
            f"{missing_owner} of {total} deals had no owner assigned"
        )
    if missing_stage > 0:
        quality_notes.append(
            f"{missing_stage} of {total} deals had no deal stage"
        )

    return clean_items, quality_notes


# ---------------------------------------------------------------------------
# Work Orders normalization
# ---------------------------------------------------------------------------

# Known execution status values (treated as an enum)
VALID_EXECUTION_STATUSES = {
    "completed", "not started", "ongoing", "executed until current month",
    "partial completed", "pause / struck", "details pending from client",
}

# Month name to number mapping
MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _parse_month_field(month_str: str, reference_date_str: str | None) -> dict:
    """
    Parse a bare month name (e.g., "Dec", "November") into a structured object.
    Uses a reference date (e.g., PO date) to infer the year, but flags the inference.
    """
    if not month_str or not month_str.strip():
        return {"raw": None, "month": None, "year_inferred": False, "inferred_year": None}

    month_str = month_str.strip().lower()
    month_num = MONTH_MAP.get(month_str)

    if month_num is None:
        return {"raw": month_str, "month": None, "year_inferred": False, "inferred_year": None}

    # Try to infer year from reference date
    inferred_year = None
    year_inferred = False
    if reference_date_str:
        ref_date = _parse_date(reference_date_str)
        if ref_date:
            try:
                ref_year = int(ref_date[:4])
                inferred_year = ref_year
                year_inferred = True
            except (ValueError, IndexError):
                pass

    return {
        "raw": month_str.capitalize(),
        "month": month_num,
        "year_inferred": year_inferred,
        "inferred_year": inferred_year,
    }


def _parse_quantity(val: str) -> dict:
    """
    Parse quantity fields that have mixed formats (e.g., "5360 HA", "57.55 HA", "40MW").
    Returns {"numeric": float|None, "unit": str|None, "raw": str}.
    """
    if not val or not val.strip():
        return {"numeric": None, "unit": None, "raw": ""}

    val = val.strip()
    # Try to extract numeric part and unit
    match = re.match(r"^([\d,]+\.?\d*)\s*(.*)$", val.replace(",", ""))
    if match:
        try:
            numeric = float(match.group(1))
            unit = match.group(2).strip() or None
            return {"numeric": numeric, "unit": unit, "raw": val}
        except ValueError:
            pass

    return {"numeric": None, "unit": None, "raw": val}


def normalize_work_orders(raw_rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Normalize raw Work Orders board data.

    Args:
        raw_rows: List of dicts from items_to_dicts() (column title -> text value)

    Returns:
        (clean_items, data_quality_notes)
    """
    clean_items = []
    quality_notes = []

    # Counters
    total = 0
    missing_execution_status = 0
    missing_sector = 0
    missing_amount = 0
    blank_delivery_date_completed = 0
    unparseable_amounts = 0
    missing_po_date = 0
    inferred_month_years = 0

    for row in raw_rows:
        # Skip embedded header rows
        if _is_header_row(row):
            continue

        total += 1

        # Extract values
        deal_name = row.get("_item_name", "") or ""
        customer_code = _find_column_value(row, "Customer Name Code", "Customer Name", "Customer Code")
        serial_num = _find_column_value(row, "Serial", "Serial #")
        nature_of_work = _find_column_value(row, "Nature of Work", "Nature")
        last_exec_month_raw = _find_column_value(row, "Last executed month", "Last executed")
        execution_status = _find_column_value(row, "Execution Status", "Execution")
        delivery_date_str = _find_column_value(row, "Data Delivery Date", "Delivery Date")
        po_date_str = _find_column_value(row, "Date of PO", "PO/LOI")
        document_type = _find_column_value(row, "Document Type")
        start_date_str = _find_column_value(row, "Probable Start Date", "Start Date")
        end_date_str = _find_column_value(row, "Probable End Date", "End Date")
        bd_personnel = _find_column_value(row, "BD/KAM Personnel", "Personnel code")
        sector = _find_column_value(row, "Sector")
        type_of_work = _find_column_value(row, "Type of Work")
        skylark_platform = _find_column_value(row, "Skylark software", "platform part")
        last_invoice_date_str = _find_column_value(row, "Last invoice date", "invoice date")
        invoice_no = _find_column_value(row, "invoice no", "latest invoice")

        # Financial fields
        amount_excl_str = _find_column_value(row, "Amount in Rupees (Excl", "Amount in Rupees (Excl of GST)")
        amount_incl_str = _find_column_value(row, "Amount in Rupees (Incl", "Amount in Rupees (Incl of GST)")
        billed_excl_str = _find_column_value(row, "Billed Value in Rupees (Excl", "Billed Value")
        billed_incl_str = _find_column_value(row, "Billed Value in Rupees (Incl")
        collected_str = _find_column_value(row, "Collected Amount")
        to_bill_excl_str = _find_column_value(row, "Amount to be billed in Rs. (Exl", "to be billed")
        to_bill_incl_str = _find_column_value(row, "Amount to be billed in Rs. (Incl")
        receivable_str = _find_column_value(row, "Amount Receivable", "Receivable")
        ar_priority = _find_column_value(row, "AR Priority", "Priority account")

        # Quantity fields
        qty_ops_str = _find_column_value(row, "Quantity by Ops")
        qty_po_str = _find_column_value(row, "Quantities as per PO")
        qty_billed_str = _find_column_value(row, "Quantity billed")
        qty_balance_str = _find_column_value(row, "Balance in quantity", "Balance")
        invoice_status = _find_column_value(row, "Invoice Status")
        billing_month_expected = _find_column_value(row, "Expected Billing Month")
        billing_month_actual = _find_column_value(row, "Actual Billing Month")
        collection_month = _find_column_value(row, "Actual Collection Month")
        wo_status = _find_column_value(row, "WO Status")
        collection_status = _find_column_value(row, "Collection status")
        collection_date_str = _find_column_value(row, "Collection Date")
        billing_status = _find_column_value(row, "Billing Status")

        # Parse dates
        delivery_date = _parse_date(delivery_date_str)
        po_date = _parse_date(po_date_str)
        start_date = _parse_date(start_date_str)
        end_date = _parse_date(end_date_str)
        last_invoice_date = _parse_date(last_invoice_date_str)
        collection_date = _parse_date(collection_date_str)

        # Parse month field with year inference
        last_exec_month = _parse_month_field(last_exec_month_raw, po_date_str)
        if last_exec_month["year_inferred"]:
            inferred_month_years += 1

        # Parse financial fields
        amount_excl = _parse_float(amount_excl_str)
        amount_incl = _parse_float(amount_incl_str)
        billed_excl = _parse_float(billed_excl_str)
        billed_incl = _parse_float(billed_incl_str)
        collected = _parse_float(collected_str)
        to_bill_excl = _parse_float(to_bill_excl_str)
        to_bill_incl = _parse_float(to_bill_incl_str)
        receivable = _parse_float(receivable_str)

        # Parse quantities
        qty_ops = _parse_quantity(qty_ops_str)
        qty_po = _parse_quantity(qty_po_str)

        # Normalize execution status (treat as enum)
        if not execution_status or not execution_status.strip():
            execution_status = "Unknown"
            missing_execution_status += 1
        else:
            execution_status = execution_status.strip()

        # Normalize sector
        if not sector or not sector.strip():
            sector = "Unspecified"
            missing_sector += 1
        else:
            sector = sector.strip()

        # Track quality issues
        if amount_excl is None and amount_excl_str and "#" in amount_excl_str:
            unparseable_amounts += 1
        if amount_excl is None and not amount_excl_str:
            missing_amount += 1
        if not po_date:
            missing_po_date += 1

        # Track blank delivery dates on completed items
        is_completed = execution_status.lower() == "completed"
        if is_completed and not delivery_date:
            blank_delivery_date_completed += 1

        # Determine if work order is overdue
        is_overdue = False
        if end_date and execution_status.lower() in ("ongoing", "not started", "executed until current month"):
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                if end_dt < date.today():
                    is_overdue = True
            except ValueError:
                pass

        clean_items.append({
            "deal_name": deal_name.strip(),
            "customer_code": customer_code.strip(),
            "serial_num": serial_num.strip(),
            "nature_of_work": nature_of_work.strip(),
            "last_executed_month": last_exec_month,
            "execution_status": execution_status,
            "data_delivery_date": delivery_date,
            "po_date": po_date,
            "document_type": document_type.strip(),
            "start_date": start_date,
            "end_date": end_date,
            "bd_personnel": bd_personnel.strip(),
            "sector": sector,
            "type_of_work": type_of_work.strip(),
            "skylark_platform": skylark_platform.strip(),
            "last_invoice_date": last_invoice_date,
            "invoice_no": invoice_no.strip(),
            "amount_excl_gst": amount_excl,
            "amount_incl_gst": amount_incl,
            "amount_display": f"₹{int(amount_excl):,}" if amount_excl else "N/A",
            "billed_excl_gst": billed_excl,
            "billed_incl_gst": billed_incl,
            "collected_amount": collected,
            "to_bill_excl_gst": to_bill_excl,
            "to_bill_incl_gst": to_bill_incl,
            "receivable": receivable,
            "ar_priority": ar_priority.strip(),
            "quantity_ops": qty_ops,
            "quantity_po": qty_po,
            "invoice_status": invoice_status.strip(),
            "billing_month_expected": billing_month_expected.strip(),
            "billing_month_actual": billing_month_actual.strip(),
            "collection_month": collection_month.strip(),
            "wo_status": wo_status.strip(),
            "collection_status": collection_status.strip(),
            "collection_date": collection_date,
            "billing_status": billing_status.strip(),
            "is_overdue": is_overdue,
            "is_completed": is_completed,
        })

    # Build quality notes
    if missing_execution_status > 0:
        quality_notes.append(
            f"{missing_execution_status} of {total} work orders had no Execution Status"
        )
    if blank_delivery_date_completed > 0:
        quality_notes.append(
            f"{blank_delivery_date_completed} of {total} work orders marked 'Completed' had no Data Delivery Date "
            f"(treated as 'not tracked', not an error)"
        )
    if unparseable_amounts > 0:
        quality_notes.append(
            f"{unparseable_amounts} work order(s) had unparseable amount values (e.g., #VALUE! errors)"
        )
    if missing_amount > 0:
        quality_notes.append(
            f"{missing_amount} of {total} work orders had no amount recorded"
        )
    if missing_sector > 0:
        quality_notes.append(
            f"{missing_sector} of {total} work orders had no sector specified"
        )
    if missing_po_date > 0:
        quality_notes.append(
            f"{missing_po_date} of {total} work orders had no PO/LOI date"
        )
    if inferred_month_years > 0:
        quality_notes.append(
            f"{inferred_month_years} work orders had a bare month name for 'Last executed month' — "
            f"year was inferred from the PO date (flagged as inferred)"
        )

    return clean_items, quality_notes
