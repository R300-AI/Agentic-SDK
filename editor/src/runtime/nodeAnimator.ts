/**
 * 節點狀態動畫排程器。
 *
 * 快節點（RuleBasedPerceive / Retrieve / Reflect 等規則式、JSON lookup等
 * 純 CPU 動作）的實際執行時長遠小於一個瀏覽器 frame（~16ms@60Hz）。
 * 同一個 frame 內 setState(running) -> setState(ok) 的兩次狀態變更
 * 只會产生一次 paint，中間的 running 狀態永遠不會被看見。
 * （這與 React batching / SSE poll cycle 無關；慢節點如 Plan / Action
 *  本來就跨多個 frame，沒有這個問題。）
 *
 * 設計關鍵：每個節點獨立計時、獨立 timer，互不阻塞。
 * `ok`/`fail` 若早於 MIN_RUNNING_VISIBLE_MS 抵達，只延後該節點的綠燈，
 * 不阻塞下一個節點的黃燈立即顯示——否則 Plan 已經在跑時，前端還會卡在
 * 上一個節點的黃燈，與 ChatPanel 顯示的「執行中(Plan)」矛盾。
 */

import type { NodeStatus } from "./types";

const MIN_RUNNING_VISIBLE_MS = 280;

type StatusUpdater = (nodeId: string, status: NodeStatus) => void;

export interface NodeAnimator {
  enqueue(nodeId: string, status: NodeStatus): void;
  reset(): void;
}

export function createNodeAnimator(updateStatus: StatusUpdater): NodeAnimator {
  const runningStartedAt: Record<string, number> = {};
  const pendingTimers: Record<string, ReturnType<typeof setTimeout>> = {};

  function clearPending(nodeId: string): void {
    const t = pendingTimers[nodeId];
    if (t !== undefined) {
      clearTimeout(t);
      delete pendingTimers[nodeId];
    }
  }

  return {
    enqueue(nodeId, status) {
      if (status === "running") {
        if (runningStartedAt[nodeId] !== undefined) return;
        clearPending(nodeId);
        runningStartedAt[nodeId] = performance.now();
        updateStatus(nodeId, "running");
        return;
      }

      const apply = () => {
        updateStatus(nodeId, status);
        delete runningStartedAt[nodeId];
        delete pendingTimers[nodeId];
      };
      const startedAt = runningStartedAt[nodeId];
      if (startedAt === undefined) {
        apply();
        return;
      }
      const elapsed = performance.now() - startedAt;
      if (elapsed >= MIN_RUNNING_VISIBLE_MS) {
        apply();
      } else {
        clearPending(nodeId);
        pendingTimers[nodeId] = setTimeout(apply, MIN_RUNNING_VISIBLE_MS - elapsed);
      }
    },
    reset() {
      for (const k of Object.keys(pendingTimers)) {
        clearTimeout(pendingTimers[k]);
        delete pendingTimers[k];
      }
      for (const k of Object.keys(runningStartedAt)) delete runningStartedAt[k];
    },
  };
}
