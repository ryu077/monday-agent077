"""
Monday.com Connection Test (Step 1 of the build).

Run this script to verify API connectivity and inspect the raw column_values
structure from both boards. Review the output before proceeding to normalization.

Usage:
    Set environment variables or create a .env file:
        MONDAY_API_TOKEN=your_token
        WORK_ORDERS_BOARD_ID=your_board_id
        DEALS_BOARD_ID=your_board_id

    Then run:
        python test_connection.py
"""

import json
import sys
from config import get_config
from monday_client import get_board_columns, fetch_all_items, get_board_name


def test_board(board_id: str, board_label: str, api_token: str):
    """Fetch and display raw data from a single board."""
    print(f"\n{'='*80}")
    print(f"  BOARD: {board_label}")
    print(f"  ID: {board_id}")
    print(f"{'='*80}")

    # Fetch board name
    try:
        name = get_board_name(board_id, api_token)
        print(f"  Board Name: {name}")
    except Exception as e:
        print(f"  ERROR fetching board name: {e}")
        return

    # Fetch column definitions
    print(f"\n--- Column Definitions ---")
    try:
        columns = get_board_columns(board_id, api_token)
        for col in columns:
            print(f"  ID: {col['id']:30s}  Title: {col['title']:50s}  Type: {col['type']}")
    except Exception as e:
        print(f"  ERROR fetching columns: {e}")
        return

    # Fetch a sample of items
    print(f"\n--- Sample Items (first 5) ---")
    try:
        items = fetch_all_items(board_id, api_token)
        print(f"  Total items fetched: {len(items)}")

        for i, item in enumerate(items[:5]):
            print(f"\n  Item {i+1}: name='{item['name']}', id={item['id']}")
            for cv in item["column_values"]:
                col_title = next(
                    (c["title"] for c in columns if c["id"] == cv["id"]),
                    cv["id"],
                )
                text_val = cv.get("text", "")
                raw_val = cv.get("value", "")
                col_type = cv.get("type", "")
                # Truncate long values for readability
                if raw_val and len(str(raw_val)) > 100:
                    raw_val = str(raw_val)[:100] + "..."
                print(f"    {col_title:50s} | text: {str(text_val):30s} | type: {col_type}")

    except Exception as e:
        print(f"  ERROR fetching items: {e}")
        return

    # Cross-board join key analysis
    return items, columns


def analyze_join_keys(deals_items, deals_columns, wo_items, wo_columns):
    """Check if cross-board join keys overlap."""
    print(f"\n{'='*80}")
    print("  CROSS-BOARD JOIN KEY ANALYSIS")
    print(f"{'='*80}")

    # Build column ID -> title maps
    deals_col_map = {c["id"]: c["title"] for c in deals_columns}
    wo_col_map = {c["id"]: c["title"] for c in wo_columns}

    # Extract client codes from Deals
    deals_client_codes = set()
    for item in deals_items:
        for cv in item["column_values"]:
            title = deals_col_map.get(cv["id"], "")
            if "client" in title.lower() and "code" in title.lower():
                val = cv.get("text", "")
                if val:
                    deals_client_codes.add(val)

    # Extract customer codes from Work Orders
    wo_customer_codes = set()
    for item in wo_items:
        for cv in item["column_values"]:
            title = wo_col_map.get(cv["id"], "")
            if "customer" in title.lower() and "code" in title.lower():
                val = cv.get("text", "")
                if val:
                    wo_customer_codes.add(val)

    print(f"\n  Deals 'Client Code' distinct values ({len(deals_client_codes)}):")
    for v in sorted(deals_client_codes)[:10]:
        print(f"    {v}")
    if len(deals_client_codes) > 10:
        print(f"    ... and {len(deals_client_codes) - 10} more")

    print(f"\n  Work Orders 'Customer Name Code' distinct values ({len(wo_customer_codes)}):")
    for v in sorted(wo_customer_codes)[:10]:
        print(f"    {v}")
    if len(wo_customer_codes) > 10:
        print(f"    ... and {len(wo_customer_codes) - 10} more")

    # Check overlap
    overlap = deals_client_codes & wo_customer_codes
    print(f"\n  Direct overlap: {len(overlap)} codes")
    if overlap:
        print(f"  Overlapping codes: {sorted(overlap)[:10]}")
    else:
        print("  WARNING: No direct overlap found between Client Code and Customer Name Code!")
        print("  The cross-board join will use Deal Name matching instead (less reliable).")

    # Check deal name overlap
    deals_names = {item["name"] for item in deals_items if item["name"]}
    wo_names = {item["name"] for item in wo_items if item["name"]}
    name_overlap = deals_names & wo_names
    print(f"\n  Deal Name overlap: {len(name_overlap)} names")
    if name_overlap:
        print(f"  Sample overlapping names: {sorted(name_overlap)[:10]}")


def main():
    config = get_config()
    api_token = config["MONDAY_API_TOKEN"]
    wo_board_id = config["WORK_ORDERS_BOARD_ID"]
    deals_board_id = config["DEALS_BOARD_ID"]

    if not api_token:
        print("ERROR: MONDAY_API_TOKEN not set.")
        print("Set it as an environment variable or in .streamlit/secrets.toml")
        sys.exit(1)

    if not wo_board_id or not deals_board_id:
        print("ERROR: Board IDs not set.")
        print("Set WORK_ORDERS_BOARD_ID and DEALS_BOARD_ID as environment variables.")
        sys.exit(1)

    print("Testing Monday.com API connection...")
    print(f"API URL: https://api.monday.com/v2")

    deals_result = test_board(deals_board_id, "Deals", api_token)
    wo_result = test_board(wo_board_id, "Work Orders", api_token)

    if deals_result and wo_result:
        deals_items, deals_cols = deals_result
        wo_items, wo_cols = wo_result
        analyze_join_keys(deals_items, deals_cols, wo_items, wo_cols)

    print(f"\n{'='*80}")
    print("  CONNECTION TEST COMPLETE")
    print("  Review the output above before proceeding to Step 2 (normalization).")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
