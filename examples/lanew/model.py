import base64
from pathlib import Path
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:18080/v1",
    api_key="local-test",
)

image_bytes = Path("sample.png").read_bytes()
image_data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")

resp = client.chat.completions.create(
    model="2",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "請描述這張圖片，並回答它可能適合什麼用途。"},
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url},
                },
            ],
        }
    ],
    max_tokens=256,
    stream=True,
)

for chunk in resp:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)

print()