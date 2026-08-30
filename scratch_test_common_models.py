import groq
from config import get_config

config = get_config()
api_key = config["GROQ_API_KEY"]
client = groq.Groq(api_key=api_key)

common_models = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}}
            }
        }
    }
]

for model in common_models:
    print(f"\nTesting {model}...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "What is the weather in Delhi?"}],
            tools=tools,
            tool_choice="auto"
        )
        print(f"Success! Tool calls: {response.choices[0].message.tool_calls}")
    except Exception as e:
        print(f"Error: {e}")
