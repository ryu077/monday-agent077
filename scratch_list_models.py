from google import genai
from config import get_config

config = get_config()
api_key = config["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

print("Listing models...")
for model in client.models.list():
    print(f"Name: {model.name}, Supported: {model.supported_actions}")
