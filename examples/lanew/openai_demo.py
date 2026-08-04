from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="local")

for chunk in client.chat.completions.create(
    model="gemma4-2b-gpu",
    messages=[{"role": "user", "content": [
        {"type": "text", "text": "簡單介紹自己"},
    ]}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)