/**
 * 節點狀態動畫佇列。
 *
 * 快節點（RuleBasedPerceive / Retrieve / Reflect 等規則式、JSON lookup等
 * 純 CPU 動作）的實際執行時長遠小於一個瀏覽器 frame（~16ms@60Hz）。
 * 同一個 frame 內 setState(running) -> setState(ok) 的兩次狀態變更
 * 只會产生一次 paint，中間的 running 狀態永遠不會被看見。
 * （這與 React batching / SSE poll cycle 無關；慢節點如 Plan / Action
 *  本來就跨多個 frame，沒有這個問題。）
 *
 * 本佇列在慢節點零影響：running 已經露面足夠久就不 sleep。
 * 只為快節點補上 MIN_RUNNING_VISIBLE_MS，讓黃色至少被 paint 一次。
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
        // 同節點重複 running（樂觀更新 + SSE 都送了）只認第一次，避免重置計時
        if (runningStartedAt[item.nodeId] === undefined) {
          updateStatus(item.nodeId, "running");
          runningStartedAt[item.nodeId] = performance.now();
        }
      } else {
        // ok / fail：等該節點黃色已露面足夠時間，再切到終態
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
