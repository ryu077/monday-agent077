import groq
from config import get_config

config = get_config()
api_key = config["GROQ_API_KEY"]
client = groq.Groq(api_key=api_key)

print("Testing groq/compound...")
try:
    response = client.chat.completions.create(
        model="groq/compound",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.1,
    )
    print("Response:", response.choices[0].message.content)
except Exception as e:
    print("Error:", e)
