from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")

print("=== models.list ===")
print(client.models.list())

print("\n=== chat.completions ===")
resp = client.with_raw_response.chat.completions.create(
    model="gemma3-4b-npu",
    messages=[{"role": "user", "content": "幫我查 2024Q4 的銷售報表並摘要"}],
)
print("HTTP status:", resp.http_response.status_code)
print("x-agentic-metadata:", resp.http_response.headers.get("x-agentic-metadata"))
completion = resp.parse()
print("model:", completion.model)
print("finish_reason:", completion.choices[0].finish_reason)
print("content:", completion.choices[0].message.content)
print("usage:", completion.usage)
