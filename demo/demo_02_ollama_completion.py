import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO_ROOT)
sys.path.insert(0, REPO_ROOT)

from agentic_sdk import Workflow
from agentic_sdk.modules import GenerativeAction, KeywordRetrieve, PassThroughPerceive


ollama_model = os.environ.get("AGENTIC_OLLAMA_MODEL", "llama3.2:1b")

workflow = Workflow(
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["tsip"],
                "content": (
                    "TSiP 是工研院主導的國產 AI 晶片落地藍圖，"
                    "重點是把國產 AI 晶片從技術規劃推進到實際應用與產業落地。"
                ),
            },
        ],
    ),
    action=GenerativeAction(
        api_key="ollama",
        base_url="http://localhost:11434/v1/",
        model=ollama_model,
        temperature=0.2,
        system_prompt=(
            "你是 Agentic SDK demo 的 Action 模組。請根據 retrieved_context 用自然語氣回答，"
            "不要逐字照抄，也不要加入 retrieved_context 沒有的外部事實。"
            "請輸出兩句繁體中文，第二句必須用『簡單說，』開頭做一句補充說明。"
        ),
    ),
)

result = workflow.run("請用自己的話介紹 TSiP，並補一句它的重點。")
print(result.final_message)