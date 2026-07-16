import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO_ROOT)
sys.path.insert(0, REPO_ROOT)

from agentic_sdk import Workflow
from agentic_sdk.modules import KeywordRetrieve, PassThroughPerceive


class SummaryAction:
    def __call__(self, memory):
        summary = memory.lookup("latest_retrieved_content") or "沒有命中任何條目。"
        return f"自訂 Action 回傳：{summary}"

workflow = Workflow(
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["agentic sdk", "sdk"],
                "content": "Agentic SDK 讓你用 workflow 組裝 agent 行為。",
            },
        ],
    ),
    action=SummaryAction(),
)

result = workflow.run("請介紹 Agentic SDK")
print(result.final_message)