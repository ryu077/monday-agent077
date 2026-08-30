import groq
import json
from config import get_config

config = get_config()
api_key = config["GROQ_API_KEY"]
client = groq.Groq(api_key=api_key)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                }
            }
        }
    }
]

print("Testing tool call on groq/compound...")
try:
    response = client.chat.completions.create(
        model="groq/compound",
        messages=[{"role": "user", "content": "What is the weather in Delhi?"}],
        tools=tools,
        tool_choice="auto",
    )
    msg = response.choices[0].message
    print("Tool calls:", msg.tool_calls)
except Exception as e:
    print("Error:", e)
