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
                "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            },
        ],
    ),
    action=GenerativeAction(
        api_key="ollama",
        base_url="http://localhost:11434/v1/",
        model=ollama_model,
        temperature=0,
        system_prompt="只根據 retrieved_context 回答。若 retrieved_context 有內容，請直接輸出其重點，不要加入任何外部知識或推測。",
    ),
)

result = workflow.run("TSiP 是什麼？")
print(result.final_message)