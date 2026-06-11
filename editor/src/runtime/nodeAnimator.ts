/**
 * 節點狀態動畫佇列。
 *
 * 後端 SSE 採 50 ms poll；mock LLM 模式下 perceive/plan/retrieve 可能在同一個 poll
 * cycle 內全部完成，事件被打包送來，React 把連續的 setState batch 成最終態，
 * 中間的 "running" 永遠不會被渲染 → 工作流視覺進程被吞掉。
 *
 * 此佇列保證每個節點的 running 狀態至少維持 MIN_RUNNING_VISIBLE_MS，
 * 把後端時序映射成符合直覺的逐節點黃→綠動畫。
 */

import type { NodeStatus } from "./types";

const MIN_RUNNING_VISIBLE_MS = 280;

type StatusUpdater = (nodeId: string, status: NodeStatus) => void;

export interface NodeAnimator {
  enqueue(nodeId: string, status: NodeStatus): void;
  reset(): void;
}

export function createNodeAnimator(updateStatus: StatusUpdater): NodeAnimator {
  let queue: Array<{ nodeId: string; status: NodeStatus }> = [];
  let processing = false;
  const runningStartedAt: Record<string, number> = {};

  const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

  async function process(): Promise<void> {
    processing = true;
    while (queue.length > 0) {
      const item = queue.shift()!;
      if (item.status === "running") {
        if (runningStartedAt[item.nodeId] === undefined) {
          updateStatus(item.nodeId, "running");
          runningStartedAt[item.nodeId] = performance.now();
        }
      } else {
        const startedAt = runningStartedAt[item.nodeId];
        if (startedAt !== undefined) {
          const elapsed = performance.now() - startedAt;
          if (elapsed < MIN_RUNNING_VISIBLE_MS) {
            await sleep(MIN_RUNNING_VISIBLE_MS - elapsed);
          }
        }
        updateStatus(item.nodeId, item.status);
        delete runningStartedAt[item.nodeId];
      }
    }
    processing = false;
  }

  return {
    enqueue(nodeId, status) {
      queue.push({ nodeId, status });
      if (!processing) void process();
    },
    reset() {
      queue = [];
      processing = false;
      for (const k of Object.keys(runningStartedAt)) delete runningStartedAt[k];
    },
  };
}
