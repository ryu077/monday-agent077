"""
Claude agent with tool calling (Step 4 of the build).

Implements the standard tool-use loop:
1. Send user message + tool definitions to Claude
2. If Claude requests a tool call, execute the corresponding Python function
3. Send tool result back to Claude
4. Get final synthesized answer

The agent always surfaces data quality caveats — never suppresses them.
"""

import json
from google import genai
from google.genai import types
from config import get_config
from tools import get_deals, get_work_orders, get_cross_board_summary, generate_leadership_summary


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tool definitions (JSON Schema for Gemini tool use)
# ---------------------------------------------------------------------------

TOOLS = [
    get_deals,
    get_work_orders,
    get_cross_board_summary,
    generate_leadership_summary,
]


# ---------------------------------------------------------------------------
# Tool dispatcher
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
# Agent handler
# ---------------------------------------------------------------------------

def handle_message(
    user_message: str,
    conversation_history: list[dict],
) -> tuple[str, list[dict]]:
    """
    Process a user message through the Gemini agent with tool calling.

    Args:
        user_message: The user's question
        conversation_history: List of prior messages [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        (assistant_response_text, updated_conversation_history)
    """
    config = get_config()
    api_key = config["GEMINI_API_KEY"]

    if not api_key:
        return "ERROR: Gemini API key is not configured. Please set GEMINI_API_KEY.", conversation_history

    client = genai.Client(api_key=api_key)

    # Convert conversation history to Gemini format if needed, but for simplicity
    # we'll just start a new chat session with history included in the prompt
    # since we want to pass tools easily via the new SDK.
    
    # We use a single prompt for this iteration to keep it simple, 
    # appending the chat history.
    history_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in conversation_history])
    full_prompt = f"Previous conversation:\n{history_text}\n\nUSER: {user_message}" if history_text else user_message

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=TOOLS,
                temperature=0.1,
            ),
        )
    except Exception as e:
        error_msg = f"Error communicating with Gemini: {str(e)}"
        return error_msg, conversation_history

    # Handle automatic tool calling by the SDK or manual processing if needed.
    # The new google-genai SDK handles tool calls automatically if they are Python functions!
    # Wait, the SDK doesn't automatically loop by default unless we use chat.
    # Let's use the chat session.
    
    chat = client.chats.create(
        model='gemini-3.6-flash',
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=TOOLS,
            temperature=0.1,
        )
    )
    
    # Replay history into the chat
    for msg in conversation_history:
        if msg["role"] == "user":
            # We can't easily push raw history without making a real call, 
            # so we'll just send the current message with context attached.
            pass
            
    # Send the actual message
    try:
        chat_response = chat.send_message(full_prompt)
        assistant_text = chat_response.text
        
        updated_history = list(conversation_history)
        updated_history.append({"role": "user", "content": user_message})
        updated_history.append({"role": "assistant", "content": assistant_text})
        
        return assistant_text, updated_history
        
    except Exception as e:
        return f"I encountered an error: {str(e)}", conversation_history
