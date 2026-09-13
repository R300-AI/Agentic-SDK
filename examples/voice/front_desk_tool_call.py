"""五個模組都用上的櫃檯 Agent：語音進、產出工具呼叫。

感知 聽（RealtimeTranscription）
規劃 決定下一步，並掛上技能包
檢索 向量查詢知識檔
反思 用規則確認查到沒有
行動 產出工具呼叫

具體內容都在檔案裡，程式碼只指路：

    examples/skills/front-desk/     技能
    examples/knowledge/front-desk.md 知識
    examples/tools/front-desk.json   工具

跑法（用一段錄好的 WAV 當麥克風，16 位元單聲道，取樣率不拘）：

    .venv/bin/python examples/voice/front_desk_tool_call.py question.wav

環境變數：對話與嵌入預設打本機 Ollama，轉寫沒有本機可用的預設，一定要給。

    CHAT_BASE_URL        預設 http://localhost:11434/v1/
    CHAT_MODEL           預設 qwen3:8b
    CHAT_API_KEY         預設 ollama
    EMBED_BASE_URL       預設同 CHAT_BASE_URL
    EMBED_MODEL          預設 nomic-embed-text
    EMBED_API_KEY        預設同 CHAT_API_KEY
    TRANSCRIBE_BASE_URL  必要
    TRANSCRIBE_MODEL     必要
    TRANSCRIBE_API_KEY   必要
"""

from __future__ import annotations

import array
import json
import os
import sys
import time
import wave
from pathlib import Path
from typing import Iterator

from agentic_sdk import Workflow
from agentic_sdk.audio.realtime import RealtimeTranscription
from agentic_sdk.core.cancellation import CancellationToken
from agentic_sdk.modules import (
    EvidenceCheckReflect,
    NextStepWithSkills,
    SemanticRetrieve,
    ToolCallAction,
    VoiceTextPerceive,
)


EXAMPLES = Path(__file__).resolve().parents[1]
SERVICE_RATE = 16000
CHUNK_SAMPLES = 1600  # 十分之一秒


def microphone_from(path: Path) -> Iterator[bytes]:
    """把 WAV 當麥克風讀，並轉成轉寫服務要的 16 kHz。"""
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1:
            raise SystemExit("需要 16 位元單聲道 WAV")
        rate = source.getframerate()
        samples = array.array("h")
        samples.frombytes(source.readframes(source.getnframes()))
    step = rate / SERVICE_RATE
    resampled = array.array("h", (samples[int(index * step)] for index in range(int(len(samples) / step))))
    for start in range(0, len(resampled), CHUNK_SAMPLES):
        yield resampled[start : start + CHUNK_SAMPLES].tobytes()


def build() -> Workflow:
    chat = {
        "api_key": os.environ.get("CHAT_API_KEY", "ollama"),
        "base_url": os.environ.get("CHAT_BASE_URL", "http://localhost:11434/v1/"),
        "model": os.environ.get("CHAT_MODEL", "qwen3:8b"),
    }
    return Workflow(
        workflow_name="櫃檯",
        perceive=VoiceTextPerceive(
            transport=RealtimeTranscription(
                api_key=os.environ["TRANSCRIBE_API_KEY"],
                base_url=os.environ["TRANSCRIBE_BASE_URL"],
                model=os.environ["TRANSCRIBE_MODEL"],
            ),
        ),
        plan=NextStepWithSkills(skill_packages=EXAMPLES / "skills" / "front-desk", **chat),
        retrieve=SemanticRetrieve(
            sources=[str(EXAMPLES / "knowledge" / "front-desk.md")],
            api_key=os.environ.get("EMBED_API_KEY", chat["api_key"]),
            base_url=os.environ.get("EMBED_BASE_URL", chat["base_url"]),
            embedding_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        ),
        reflect=EvidenceCheckReflect(),
        action=ToolCallAction(
            tools=json.loads((EXAMPLES / "tools" / "front-desk.json").read_text(encoding="utf-8")),
            **chat,
        ),
    )


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)

    workflow = build()
    perceive = workflow.modules["perceive"]

    print("正在聽…")
    for chunk in microphone_from(Path(sys.argv[1])):
        perceive.hear(chunk)  # 安靜的片段不會離開這台機器
        time.sleep(CHUNK_SAMPLES / SERVICE_RATE)  # 麥克風是即時到達的

    # 轉寫服務靠聽到靜默判斷一句話結束，文字會在說完之後才到。
    waited = 0.0
    while not perceive.pending_input() and waited < 10:
        time.sleep(0.2)
        waited += 0.2
    if not perceive.pending_input():
        print("沒有聽到任何話。")
        return 1
    print(f"聽到：{perceive.pending_input()}")

    # token 是「被插話」抵達一個已在跑的執行的方式：感知模組握著它。
    result = workflow.run(cancel=CancellationToken())

    print(f"回覆：{result.final_message}")
    for call in result.entities.get("latest_tool_calls", []):
        # 這個模組只交出呼叫，不會替你打那個 API；執行與把結果餵回下一輪是你的事。
        print(f"要呼叫：{call['function']['name']}({call['function']['arguments']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
