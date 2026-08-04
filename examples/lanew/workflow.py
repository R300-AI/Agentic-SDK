import os

from agentic_sdk import EvidenceCheckReflect, Workflow
from agentic_sdk.modules import TextImagePerceive, NextStepPlan, SemanticRetrieve, EvidenceCheckReflect, ToolCallAction

azure_embeddings_api_key = os.environ.get("AGENTIC_SDK_AZURE_EMBEDDINGS_API_KEY")
if not azure_embeddings_api_key:
    raise RuntimeError("Set AGENTIC_SDK_AZURE_EMBEDDINGS_API_KEY before running this example.")

workflow = Workflow(
    workflow_name="LaNew鞋墊顧問",
    description="根據使用者提供的足測報告圖片與問題，整理足部量測、足壓與腳形資訊，查找 LaNew 產品資料，推薦合適鞋墊，並詢問使用者是否購買推薦產品。",
    perceive=TextImagePerceive(api_key="local", base_url="http://localhost:8000/v1", model="gemma-4-2b"),
    plan=NextStepPlan(api_key="local", base_url="http://localhost:8000/v1", model="gemma-4-2b", retrieve_description="優先從這批參考文件查找：查找 LaNew 產品資訊、鞋墊建議、適用條件、支撐特性、楦頭或寬腳適配、價格、商品編號與限制條件。"),
    retrieve=SemanticRetrieve(
        api_key=azure_embeddings_api_key,
        base_url="https://agentic-sdk-foundry.cognitiveservices.azure.com/openai/deployments/text-embedding-3-large/embeddings?api-version=2023-05-15",
        embedding_model="text-embedding-3-large",
        sources=[
                    "./lanew_footwear_catalog.md"
                ],
    ),
    reflect=EvidenceCheckReflect(on_failure="end"),
    action=ToolCallAction(api_key="local", base_url="http://localhost:8000/v1", model="gemma-4-2b", system_prompt="互動元件使用原則：\n請先判斷使用者這一輪的意圖類型，而不是因為已配置互動元件就要求使用者選擇。\n當使用者只是詢問資訊、要求分析、要求解釋、比較原因、了解現況或追問依據時，只用自然語言回答，不要提出確認問題。\n只有當使用者明確進入決策、確認、提交、申請、送出表單、安排後續流程或選擇下一步，且該需求符合工具描述時，才提出互動確認。\n需要互動確認時，請先完整輸出你的建議、依據、限制與下一步，最後用自然語言提出清楚的確認問題；Playground 會依配置顯示互動元件並收集使用者選擇。\n不要把 API URL、component schema、欄位 JSON 或內部工具設定當成使用者可見文字輸出。\n\n使用者設定的回覆規範：\n你是 LaNew 門市鞋墊顧問。請先判斷使用者意圖。\n當使用者只是詢問足測結果、足部狀況、數據代表意義、壓力分布、左右腳差異、足弓判讀或推薦依據時，只回覆文字分析，不推薦產品，也不要詢問是否購買。\n當使用者明確要求推薦、比較、挑選、購買建議、久站通勤選擇、寬腳適配、正式外型搭配或下一步決策時，請根據足測報告與 LaNew 產品資料推薦合適鞋墊或鞋款，說明推薦依據、商品名稱、", tools=[
            {
                "type": "function",
                "function": {
                    "name": "submit_api_1",
                    "description": "顯示互動元件並收集使用者選擇。 僅在本輪已完成具體產品推薦，且需要使用者確認是否購買、保留推薦、送出需求或進入下一步時呼叫。若使用者只是要求分析、解釋、查詢足測結果、追問理由、比較原因或補充條件，不要呼叫工具。 API：POST https://example.com/lanew/recommendation/confirm",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "是否進行下一步": {
                                "type": "boolean",
                                "description": "使用者是否確認要購買、保留或送出本次推薦。若使用者尚未回答，請先用 false 作為暫定值來顯示確認面板。"
                            }
                        },
                        "required": [
                            "是否進行下一步"
                        ],
                        "additionalProperties": False
                    }
                }
            }
        ], tool_choice="none"),
)

def on_event(event):
    if event["type"] == "stage" and event["phase"] == "start":
        print(f"\n【{event['module']}】{event['label']}")
    elif event["type"] == "token_delta":
        print(event["content"], end="", flush=True)


stream = workflow.stream(
    "請為我推薦合適的鞋墊。",
    event_callback=on_event,
)

for content in stream:
    print(content, end="", flush=True)

result = stream.result