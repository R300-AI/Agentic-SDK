from agentic_sdk import Workflow
from agentic_sdk.modules import GenerativeAction, KeywordRetrieve, TextPerceive

def on_event(event):
    if event["type"] == "stage" and event["phase"] == "start":
        print(f"【STAGE】{event['label']}")
    elif event["type"] == "stage" and event["phase"] == "finish":
        for item in event["fields"]:
            print(f"{item['field']}：{item['value']}")

workflow = Workflow(
  
  perceive=TextPerceive(api_key="local", base_url="http://localhost:8000/v1", model="gemma-4-2b"),
  retrieve=KeywordRetrieve(items=[{
    "keywords": ["tsip"],
    "content": (
        "TSiP 是國產晶片落地平台，目標是整合晶片設計、"
        "軟體與應用驗證，縮短產品從研發到導入的週期。"
    ),
  }]),
  action=GenerativeAction(api_key="local", base_url="http://localhost:8000/v1", model="gemma-4-2b"),
  
)

print(workflow.run("請用一句話解釋 TSiP 的目的", event_callback=on_event).final_message)