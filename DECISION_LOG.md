# Decision Log

## Key Assumptions

1. **Data is masked but proportionally accurate.** Deal values and amounts are masked (multiplied by a constant) for confidentiality. We treat them as real values for relative comparisons, aggregations, and ranking — the ratios and proportions remain valid even if absolute numbers are obscured.

2. **"This quarter" defaults to the current calendar quarter** unless the user specifies otherwise. The agent states this assumption explicitly in its response rather than asking a clarifying question.

3. **Deal names are the best available cross-board join key.** The customer code columns use different naming schemes across boards (Deals: `COMPANY_XXX`, Work Orders: `WOCOMPANY_XXX`) with no direct overlap. Deal names (anime character names) appear in both boards and provide a partial match, but are not unique identifiers — multiple deals/work orders can share the same name. This limitation is documented in every cross-board response.

4. **Embedded header rows in the CSV data will persist in Monday.com.** The source Deals CSV contains rows where column values are literally the column headers repeated (rows 57 and 189 in the raw CSV). These are detected and skipped during normalization by checking if multiple values match known header text.

5. **"Overdue" means past the Probable End Date but not marked Completed.** Work orders are flagged as overdue if their end date has passed and their execution status is still "Ongoing", "Not Started", or similar. This is a heuristic — some WOs may legitimately extend beyond their original end date.

## Trade-offs and Why

| Decision | Alternative Considered | Why This Choice |
|---|---|---|
| **Direct Monday.com GraphQL API** over MCP | MCP server for Monday.com | The GraphQL API is simpler, has no additional dependencies, and gives full control over queries and pagination. MCP would add unnecessary abstraction for a read-only use case. |
| **No caching** | Redis/in-memory cache | Time-constrained build. Every query hits Monday.com live, ensuring data freshness. Cache would improve latency but adds complexity around invalidation. Noted as a future improvement. |
| **Column matching by title (fuzzy)** | Column matching by ID | Monday.com assigns random IDs on CSV import. Title-based matching is more resilient to re-imports and board recreation. We use case-insensitive partial matching to handle title truncation. |
| **Streamlit** over custom React/Next.js | Custom frontend with charts | Streamlit is the fastest path to a working chat UI. The assignment values data correctness over visual polish. A custom frontend would take 3-4x longer for marginal UX improvement. |
| **Claude Sonnet 4** as the LLM | GPT-4, Gemini, open-source models | Claude's tool-calling is robust and well-documented. Sonnet 4 provides excellent reasoning at a reasonable cost. The structured tool-use loop is cleaner than function calling in other APIs. |
| **Single tool call per query** (agent decides) | Hardcoded multi-tool pipelines | Letting Claude decide which tool(s) to call is more flexible and handles edge cases better than routing logic. The trade-off is occasional unnecessary API calls, but reliability is higher. |

## What Would Be Improved With More Time

1. **Caching layer** — Cache board data for 5 minutes to reduce API calls. Monday.com's free plan has rate limits (60 req/min). A simple `@st.cache_data(ttl=300)` would help.

2. **Streaming responses** — Currently waits for the full response. Streaming would improve perceived latency.

3. **Richer cross-board analysis** — Build a proper entity resolution pipeline to match customers across boards, possibly using fuzzy matching on customer names or manual mapping tables.

4. **Charts and visualizations** — Add Plotly charts for pipeline funnel, sector distribution, and billing status. The data is already structured for this in `generate_leadership_summary`.

5. **Multi-turn memory** — Current conversation history is maintained but not used strategically. Could implement context-aware follow-up (e.g., "drill into that" referring to the last sector mentioned).

6. **Retry logic** — Currently uses basic try/except. A proper retry with exponential backoff would handle transient API failures more gracefully.

7. **Comprehensive unit tests** — Test normalization functions against known edge cases (header rows, #VALUE! errors, blank fields).

## How "Leadership Updates" Was Interpreted

The assignment states: *"The agent should help prepare data for leadership updates."*

**Interpretation:** An on-demand structured summary generated via the `generate_leadership_summary` tool function, triggered when the user asks questions like "Give me a leadership update" or "What should I tell the board?"

**What it produces:**
- Open pipeline overview (value by sector and by stage)
- Deals won this quarter (count and value)
- Stuck deals — those sitting in the pipeline for >30 days without progression
- Stalled/overdue work orders — past their probable end date but still active
- Work order financials — total contract value, billed, collected, receivable
- Data completeness metrics — what percentage of deals have probability ratings, values, and close dates

**What it is NOT:** A scheduled automated report or a PowerPoint generator. With more time, this could export to PDF/slides, but the core insight delivery is conversational — a founder types "give me an update for the board meeting" and gets a structured, caveated response they can immediately use.
