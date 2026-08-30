import groq
from config import get_config

config = get_config()
api_key = config["GROQ_API_KEY"]
client = groq.Groq(api_key=api_key)

print("Listing Groq models...")
try:
    for model in client.models.list().data:
        print(f"ID: {model.id}")
except Exception as e:
    print(f"Error: {e}")
