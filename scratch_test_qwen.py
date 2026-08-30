import groq
from config import get_config

config = get_config()
api_key = config["GROQ_API_KEY"]
client = groq.Groq(api_key=api_key)

models_to_test = [
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b"
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

for model in models_to_test:
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
