import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO_ROOT)
sys.path.insert(0, REPO_ROOT)

from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, KeywordRetrieve, PassThroughPerceive

workflow = Workflow(
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["agentic sdk", "sdk"],
                "content": "Agentic SDK 是一個以 workflow 組裝 agent 行為的 Python library。",
            },
            {
                "keywords": ["tsip"],
                "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            },
        ],
    ),
    action=DirectAnswerAction(),
)

result = workflow.run("TSiP 是什麼？")
print(result.final_message)