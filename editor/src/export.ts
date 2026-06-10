/** M6-10 — 雙重輸出:把 WorkflowConfig 渲染成可直接執行的 Python 片段。
 *
 * 與 SDK 端 `Workflow.from_config()` 對齊;讀者只要複製貼上即可在自己的環境跑。
 */

import type { WorkflowConfig } from "./types";
import { configToYaml } from "./adapter";

export function configToPython(config: WorkflowConfig): string {
  const yamlText = configToYaml(config);
  const indentedYaml = yamlText
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((l) => (l.length === 0 ? "" : l))
    .join("\n");

  const wfName = config.name ?? "demo";

  return `"""由 Agentic SDK Editor 自動生成。
等價於透過 Workflow.from_config(WorkflowConfig.from_dict(yaml.safe_load(...))) 載入。
"""

import asyncio
import yaml

from agentic_sdk.memory import MemoryStore
from agentic_sdk.workflow.config import WorkflowConfig
from agentic_sdk.workflow.engine import Workflow


WORKFLOW_YAML = """\n${indentedYaml}"""


async def main(user_message: str) -> str:
    config = WorkflowConfig.from_dict(yaml.safe_load(WORKFLOW_YAML))
    memory = MemoryStore(db_path=".memory/${wfName}.sqlite")
    wf = Workflow.from_config(config, memory_store=memory)
    result = await wf.run(user_message)
    return result.final_message or ""


if __name__ == "__main__":
    answer = asyncio.run(main("你好,我想了解這個 workflow"))
    print(answer)
`;
}
