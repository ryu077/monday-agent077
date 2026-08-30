"""
BI Agent Module (Step 4 of the build).

Supports BOTH Gemini (Google GenAI) and Groq (Llama 3) dynamically.
If GROQ_API_KEY is configured, it runs via Groq (extremely fast & free with no 503s).
Otherwise, it falls back to Gemini.

Includes automatic exponential backoff retries to handle API congestion.
"""

import json
import time
from google import genai
from google.genai import types
from google.genai.errors import APIError
from config import get_config
from tools import get_deals, get_work_orders, get_cross_board_summary, generate_leadership_summary

# System prompt is shared across both providers
SYSTEM_PROMPT = """You are a business intelligence analyst for a drone services company (similar to Skylark Drones). You help founders and executives get quick, accurate answers to business questions by querying live data from two Monday.com boards:

1. **Deals Board** — Sales pipeline data including deal names, stages, sectors, values, closure probabilities, and statuses (Open/Won/Dead).
2. **Work Orders Board** — Project execution data including work order details, execution status, financials (amounts, billing, collections), sectors, and delivery dates.

## Your Behavior

- **Be concise and actionable.** Founders are busy — lead with the key insight, then provide supporting details.
- **Always surface data quality caveats.** When the tools return data quality notes, include the relevant ones in your response. Never suppress or silently resolve data quality issues.
- **State assumptions explicitly.** If a query is ambiguous (e.g., "this quarter" with no date reference), state your assumption (e.g., "Assuming you mean Q3 2026") and proceed. Do NOT ask clarifying questions unless the query is genuinely uninterpretable.
- **Use concrete numbers.** When discussing pipeline value, counts, or financials, always include the actual numbers.
- **Format for readability.** Use bullet points, bold text, and tables where they help. Keep responses scannable.
- **Acknowledge limitations.** If the cross-board join is unreliable or data is incomplete, say so upfront rather than presenting uncertain data as fact.

## Important Notes on the Data

- Deal values are masked (multiplied by a constant) for confidentiality — treat them as real values for relative comparisons and aggregations.
- Customer/client codes use different naming schemes across the two boards (COMPANY_XXX in Deals vs WOCOMPANY_XXX in Work Orders), so cross-board matching is done by deal name, which is less reliable.
- Closure Probability uses text labels (High/Medium/Low) — many deals have no probability rating ("unrated").
- Deal Stage uses lettered prefixes (A through O) that encode the funnel order from early (A. Lead Generated) to late (H. Work Order Received, G. Project Won).

## Sectors You'll See
Mining, Renewables, Powerline, Railways, Construction, DSP, Others, Security and Surveillance, Manufacturing, Tender, Aviation
"""

# Gemini Python Function Tools
GEMINI_TOOLS = [
    get_deals,
    get_work_orders,
    get_cross_board_summary,
    generate_leadership_summary,
]

# Groq / OpenAI JSON Schema Tools
GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_deals",
            "description": "Fetch and filter deals from the Deals board to answer questions about the sales pipeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Filter by sector name (e.g. Mining, Renewables)"},
                    "status": {"type": "string", "enum": ["Open", "Won", "Dead", "On Hold"], "description": "Filter by deal status"},
                    "min_probability": {"type": "string", "enum": ["Low", "Medium", "High"], "description": "Filter by minimum closure probability"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_orders",
            "description": "Fetch and filter work orders from the Work Orders board to answer questions about execution and billing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Filter by sector name"},
                    "status": {"type": "string", "description": "Filter by execution status (e.g. Completed, Ongoing)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cross_board_summary",
            "description": "Attempt to join deals and work orders by deal name for a cross-board view.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_leadership_summary",
            "description": "Produce a structured executive summary suitable for leadership updates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter"},
                    "quarter": {"type": "string", "description": "Optional quarter filter (e.g. Q1 2026)"}
                }
            }
        }
    }
]


# ---------------------------------------------------------------------------
# Tool Dispatcher (Shared)
# ---------------------------------------------------------------------------

def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool function and return the result as a JSON string."""
    tool_map = {
        "get_deals": get_deals,
        "get_work_orders": get_work_orders,
        "get_cross_board_summary": get_cross_board_summary,
        "generate_leadership_summary": generate_leadership_summary,
    }

    func = tool_map.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        results, quality_notes = func(**tool_input)
        return json.dumps({
            "results": results,
            "data_quality_notes": quality_notes,
        }, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "data_quality_notes": [f"Tool execution error: {str(e)}"],
        })


# ---------------------------------------------------------------------------
# Providers Implementation
# ---------------------------------------------------------------------------

def _handle_gemini(user_message: str, conversation_history: list[dict], api_key: str) -> tuple[str, list[dict]]:
    """Query Gemini 3.5 Flash Lite with automatic retries."""
    client = genai.Client(api_key=api_key)
    
    # Build prompt with history
    history_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in conversation_history])
    full_prompt = f"Previous conversation:\n{history_text}\n\nUSER: {user_message}" if history_text else user_message

    chat = client.chats.create(
        model='gemini-3.5-flash-lite',
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=GEMINI_TOOLS,
            temperature=0.1,
        )
    )
    
    max_retries = 4
    for attempt in range(max_retries):
        try:
            chat_response = chat.send_message(full_prompt)
            assistant_text = chat_response.text
            
            updated_history = list(conversation_history)
            updated_history.append({"role": "user", "content": user_message})
            updated_history.append({"role": "assistant", "content": assistant_text})
            
            return assistant_text, updated_history
        except APIError as e:
            is_transient = "503" in str(e) or "429" in str(e) or "UNAVAILABLE" in str(e)
            if is_transient and attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            return f"Error communicating with Gemini (503/429/UNAVAILABLE after {attempt+1} attempts). Consider adding a free `GROQ_API_KEY` to secrets for 100% uptime.", conversation_history
        except Exception as e:
            return f"I encountered an error: {str(e)}", conversation_history


def _handle_groq(user_message: str, conversation_history: list[dict], api_key: str) -> tuple[str, list[dict]]:
    """Query Groq (Llama 3.3 70B) using standard tool calling loop."""
    import groq
    client = groq.Groq(api_key=api_key)
    
    # Format messages for Groq API
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    
    max_iterations = 5
    for _ in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=messages,
                tools=GROQ_TOOLS,
                tool_choice="auto",
                temperature=0.1,
            )
        except Exception as e:
            return f"Error communicating with Groq: {str(e)}", conversation_history

        response_message = response.choices[0].message
        messages.append(response_message)

        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                tool_output = _execute_tool(function_name, function_args)
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": tool_output,
                })
            # Continue the loop to get final response
            continue
        else:
            # We got a final text answer
            assistant_text = response_message.content
            
            updated_history = list(conversation_history)
            updated_history.append({"role": "user", "content": user_message})
            updated_history.append({"role": "assistant", "content": assistant_text})
            
            return assistant_text, updated_history

    return "Groq exceeded maximum tool call iterations. Please try again.", conversation_history


# ---------------------------------------------------------------------------
# Main Handler (Routes based on credentials)
# ---------------------------------------------------------------------------

def handle_message(
    user_message: str,
    conversation_history: list[dict],
) -> tuple[str, list[dict]]:
    """
    Process a user message through the routed provider.
    Routes to Groq if GROQ_API_KEY is present, otherwise falls back to Gemini.
    """
    config = get_config()
    
    groq_key = config.get("GROQ_API_KEY")
    gemini_key = config.get("GEMINI_API_KEY")

    if groq_key:
        return _handle_groq(user_message, conversation_history, groq_key)
    elif gemini_key:
        return _handle_gemini(user_message, conversation_history, gemini_key)
    else:
        return (
            "ERROR: Neither GEMINI_API_KEY nor GROQ_API_KEY is configured. "
            "Please configure at least one API key in `.streamlit/secrets.toml` or environment variables.",
            conversation_history
        )
