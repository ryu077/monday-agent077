# Monday.com Business Intelligence Agent

An AI-powered business intelligence agent that answers founder-level questions by querying live data from Monday.com boards. Built with Claude (Anthropic) for natural language understanding and Streamlit for the conversational interface.

## Architecture Overview

```
User Question
    │
    ▼
┌──────────────┐
│  app.py      │  Streamlit chat interface
│  (UI Layer)  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  agent.py    │  Claude tool-calling loop
│  (AI Layer)  │  System prompt + tool schemas
└──────┬───────┘
       │ Claude decides which tool(s) to call
       ▼
┌──────────────┐
│  tools.py    │  4 tool functions:
│  (Data Layer)│  get_deals, get_work_orders,
│              │  get_cross_board_summary,
│              │  generate_leadership_summary
└──────┬───────┘
       │ Each tool calls normalize.py internally
       ▼
┌──────────────┐
│ normalize.py │  Data cleaning & quality tracking
│ (Transform)  │  Handles all known data quirks
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ monday_client.py │  GraphQL API client
│ (API Layer)      │  Pagination, auth, raw data fetch
└──────────────────┘
       │
       ▼
  Monday.com API
  (Live Data)
```

**Key Design Principle:** Every user query triggers a live API call to Monday.com. Nothing is cached or hardcoded. Data quality issues are tracked at every layer and surfaced to the user — never silently suppressed.

## Setup Instructions

### Prerequisites
- Python 3.11+
- A Monday.com account with two boards (Work Orders and Deals)
- An Anthropic API key

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/monday-bi-agent.git
cd monday-bi-agent
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Import Data into Monday.com
1. Create a Monday.com account at [monday.com](https://monday.com)
2. Create a new board named **"Work Orders"**
   - Click the `+` button → Import → Upload the `Work_Order_Tracker Data.xlsx` file
   - **Note:** The first row of this file is empty — Monday.com should skip it and use row 2 as headers. If not, delete the empty first row before importing.
3. Create another board named **"Deals"**
   - Import the `Deal funnel Data.xlsx` file
4. Note the **Board IDs** from the URL bar when viewing each board:
   `https://your-account.monday.com/boards/XXXXXXXXX` ← this number

### 4. Get API Keys
- **Monday.com API Token:** Go to your avatar (bottom-left) → Developers → My Access Tokens
- **Anthropic API Key:** Sign up at [console.anthropic.com](https://console.anthropic.com) → API Keys

### 5. Configure Secrets

**Option A: Environment variables (local development)**
```bash
export MONDAY_API_TOKEN="your_monday_token"
export ANTHROPIC_API_KEY="your_anthropic_key"
export WORK_ORDERS_BOARD_ID="your_wo_board_id"
export DEALS_BOARD_ID="your_deals_board_id"
```

**Option B: Streamlit secrets (recommended)**
Create `.streamlit/secrets.toml`:
```toml
MONDAY_API_TOKEN = "your_monday_token"
ANTHROPIC_API_KEY = "your_anthropic_key"
WORK_ORDERS_BOARD_ID = "your_wo_board_id"
DEALS_BOARD_ID = "your_deals_board_id"
```

### 6. Test the Connection
```bash
python test_connection.py
```
This will verify API connectivity, print column structures, and analyze cross-board join key compatibility.

### 7. Run the App
```bash
streamlit run app.py
```

## File Structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit chat interface |
| `agent.py` | Claude tool-calling agent |
| `tools.py` | 4 tool functions (deals, work orders, cross-board, leadership summary) |
| `normalize.py` | Data cleaning and quality tracking |
| `monday_client.py` | Monday.com GraphQL API client |
| `config.py` | Configuration management (secrets) |
| `test_connection.py` | API connection test and data inspection script |
| `DECISION_LOG.md` | Key assumptions, trade-offs, and design decisions |

## Deployment (Streamlit Community Cloud)

1. Push this repo to a public GitHub repository
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo → select `app.py` as the main file
4. Add secrets in the Streamlit Cloud dashboard (Settings → Secrets):
   ```toml
   MONDAY_API_TOKEN = "..."
   ANTHROPIC_API_KEY = "..."
   WORK_ORDERS_BOARD_ID = "..."
   DEALS_BOARD_ID = "..."
   ```
5. Deploy and verify in an incognito browser window
