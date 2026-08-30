# Monday.com Business Intelligence Agent

An AI-powered business intelligence agent that answers founder-level questions by querying live data from Monday.com boards. Built with a multi-provider LLM architecture (Groq / Google Gemini) for natural language understanding and Streamlit for the conversational interface.

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
│  agent.py    │  LLM tool-calling loop (multi-provider)
│  (AI Layer)  │  System prompt + tool schemas
└──────┬───────┘
       │ LLM decides which tool(s) to call
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

**Key Design Principles:**
- Every user query triggers a live API call to Monday.com. Nothing is cached or hardcoded.
- Data quality issues are tracked at every layer and surfaced to the user — never silently suppressed.
- The agent is provider-agnostic: it supports multiple LLM backends (Groq, Google Gemini) with automatic routing based on which API key is configured.

## LLM Provider Support

The agent supports multiple LLM providers for maximum flexibility and uptime:

| Provider | Model | Free Tier | Tool Calling |
|---|---|---|---|
| **Groq** (Primary) | `qwen/qwen3.8-27b` | ✅ Free (8K TPM) | ✅ Native |
| **Google Gemini** (Fallback) | `gemini-3.5-flash-lite` | ✅ Free | ✅ Native (AFC) |

**Routing logic:** If `GROQ_API_KEY` is configured, the agent routes to Groq. Otherwise, it falls back to Gemini with exponential backoff retries (2s → 4s → 8s) to handle transient 503 errors.

> **Note:** The architecture is designed to be provider-agnostic. Adding support for Anthropic Claude, OpenAI GPT-4, or any other provider with tool-calling support requires only adding a new `_handle_<provider>` function in `agent.py` — no changes to the data pipeline, tools, or UI.

## Known Limitations

1. **Free-tier token limits:** Groq's free tier has an 8,000 tokens-per-minute limit. To stay within this limit, tool results are slimmed down to essential fields only (8-9 per item) and capped at 15 items per query. For broad questions (e.g., "show me everything"), use the `generate_leadership_summary` tool which returns pre-aggregated data.

2. **Cross-board join quality:** Customer codes use different naming schemes across the Deals board (`COMPANY_XXX`) and Work Orders board (`WOCOMPANY_XXX`) with zero direct overlap. Cross-board matching falls back to Deal Name matching, which is less reliable since names like "Sakura" appear across multiple unrelated deals. This limitation is explicitly surfaced to the user in every cross-board query response.

3. **No caching:** Every query hits Monday.com live. This ensures data freshness but adds latency (~2-3 seconds per query for API calls). A caching layer (e.g., `@st.cache_data(ttl=300)`) would improve performance.

## Setup Instructions

### Prerequisites
- Python 3.11+
- A Monday.com account with two boards (Work Orders and Deals)
- A Groq API key (free) OR a Google Gemini API key (free)

### 1. Clone the Repository
```bash
git clone https://github.com/ryu077/monday-agent077.git
cd monday-agent077
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
- **Groq API Key (recommended):** Sign up at [console.groq.com](https://console.groq.com) → API Keys (free, no credit card needed)
- **Google Gemini API Key (alternative):** Get from [aistudio.google.com](https://aistudio.google.com)

### 5. Configure Secrets

**Option A: Environment variables (local development)**
```bash
export MONDAY_API_TOKEN="your_monday_token"
export GROQ_API_KEY="your_groq_key"
export WORK_ORDERS_BOARD_ID="your_wo_board_id"
export DEALS_BOARD_ID="your_deals_board_id"
```

**Option B: Streamlit secrets (recommended)**
Create `.streamlit/secrets.toml`:
```toml
MONDAY_API_TOKEN = "your_monday_token"
GROQ_API_KEY = "your_groq_key"
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
| `agent.py` | Multi-provider LLM agent with tool-calling (Groq + Gemini) |
| `tools.py` | 4 tool functions (deals, work orders, cross-board, leadership summary) |
| `normalize.py` | Data cleaning and quality tracking |
| `monday_client.py` | Monday.com GraphQL API client |
| `config.py` | Configuration management (secrets) |
| `test_connection.py` | API connection test and data inspection script |
| `DECISION_LOG.md` | Key assumptions, trade-offs, and design decisions |
| `result_samples/` | Screenshots of agent responses |

## Deployment (Streamlit Community Cloud)

1. Push this repo to a public GitHub repository
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo → select `app.py` as the main file
4. Add secrets in the Streamlit Cloud dashboard (Settings → Secrets):
   ```toml
   MONDAY_API_TOKEN = "..."
   GROQ_API_KEY = "..."
   WORK_ORDERS_BOARD_ID = "..."
   DEALS_BOARD_ID = "..."
   ```
5. Deploy and verify in an incognito browser window
