"""
Monday.com GraphQL API client.
Handles authentication, pagination, and raw data fetching from boards.
All data flows through this module — nothing is hardcoded.
"""

import requests
from config import MONDAY_API_URL, get_config


def _make_request(query: str, api_token: str) -> dict:
    """Execute a GraphQL query against the Monday.com API."""
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }
    response = requests.post(
        MONDAY_API_URL,
        json={"query": query},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        error_msgs = [e.get("message", str(e)) for e in data["errors"]]
        raise RuntimeError(f"Monday.com API errors: {'; '.join(error_msgs)}")

    return data


def get_board_columns(board_id: str, api_token: str) -> list[dict]:
    """
    Fetch column definitions for a board.
    Returns list of dicts: [{"id": "col_id", "title": "Column Title", "type": "column_type"}, ...]
    """
    query = f"""
    query {{
        boards(ids: [{board_id}]) {{
            name
            columns {{
                id
                title
                type
            }}
        }}
    }}
    """
    data = _make_request(query, api_token)
    boards = data.get("data", {}).get("boards", [])
    if not boards:
        raise RuntimeError(f"Board {board_id} not found or not accessible.")
    return boards[0]["columns"]


def get_board_name(board_id: str, api_token: str) -> str:
    """Fetch the display name of a board."""
    query = f"""
    query {{
        boards(ids: [{board_id}]) {{
            name
        }}
    }}
    """
    data = _make_request(query, api_token)
    boards = data.get("data", {}).get("boards", [])
    if not boards:
        return f"Board {board_id}"
    return boards[0]["name"]


def fetch_all_items(board_id: str, api_token: str) -> list[dict]:
    """
    Fetch ALL items from a board, handling cursor-based pagination.
    Returns list of raw item dicts, each with 'id', 'name', and 'column_values'.
    """
    all_items = []

    # First page
    query = f"""
    query {{
        boards(ids: [{board_id}]) {{
            items_page(limit: 500) {{
                cursor
                items {{
                    id
                    name
                    column_values {{
                        id
                        text
                        value
                        type
                    }}
                }}
            }}
        }}
    }}
    """
    data = _make_request(query, api_token)
    boards = data.get("data", {}).get("boards", [])
    if not boards:
        raise RuntimeError(f"Board {board_id} not found.")

    page = boards[0]["items_page"]
    all_items.extend(page["items"])
    cursor = page.get("cursor")

    # Subsequent pages
    while cursor:
        query = f"""
        query {{
            next_items_page(limit: 500, cursor: "{cursor}") {{
                cursor
                items {{
                    id
                    name
                    column_values {{
                        id
                        text
                        value
                        type
                    }}
                }}
            }}
        }}
        """
        data = _make_request(query, api_token)
        page = data.get("data", {}).get("next_items_page", {})
        all_items.extend(page.get("items", []))
        cursor = page.get("cursor")

    return all_items


def items_to_dicts(items: list[dict], columns: list[dict]) -> list[dict]:
    """
    Convert raw Monday.com items into flat dictionaries keyed by column title.
    The item 'name' (first column) is included as '_item_name'.
    The item 'id' is included as '_item_id'.
    """
    col_id_to_title = {col["id"]: col["title"] for col in columns}

    result = []
    for item in items:
        row = {
            "_item_id": item["id"],
            "_item_name": item.get("name", ""),
        }
        for cv in item.get("column_values", []):
            title = col_id_to_title.get(cv["id"], cv["id"])
            row[title] = cv.get("text", "") or ""
        result.append(row)

    return result
