/**
 * 節點狀態動畫排程器（嚴格序列 FIFO 版）。
 *
 * 設計目的:讓使用者看得到每個節點 idle → running → ok 的視覺敘事順序，
 * 即使後端事件被 Cloud Run / GFE buffer 之後一次到齊。
 *
 * 行為契約:
 *   1. 所有 enqueue 進入單一 FIFO 佇列，逐一 apply
 *   2. 兩次 apply 之間至少間隔 minVisibleMs（預設 350ms），確保前一個
 *      狀態在視覺上停留足夠久
 *   3. 同節點重複 status 直接 dedupe（避免 SSE 重送）
 *   4. reset() 清空佇列與計時器
 *
 * 為什麼是嚴格序列而非 per-node 獨立:
 *   - 後端 node_span 的 emit 順序本來就是絕對序列
 *   - per-node 獨立會讓 SSE buffer flush 時多個節點同時呈現 running，
 *     使用者無法區分「先 perceive 再 plan」與「同時 perceive + plan」
 *   - 嚴格序列保證視覺敘事 = 後端 emit 敘事
 *   - 代價：視覺進度可能落後實際後端進度（5 節點 × 2 transitions ×
 *     350ms ≈ 3.5s），但遠小於 LLM 本身的 20+s
 */

import type { NodeStatus } from "./types";

export const MIN_VISIBLE_STATE_MS = 350;

type StatusUpdater = (nodeId: string, status: NodeStatus) => void;

export interface NodeAnimator {
  enqueue(nodeId: string, status: NodeStatus): void;
  reset(): void;
}

interface Transition {
  nodeId: string;
  status: NodeStatus;
}

export interface NodeAnimatorOptions {
  /** 兩個 transition 之間至少間隔多少毫秒。預設 MIN_VISIBLE_STATE_MS。 */
  minVisibleMs?: number;
  /** 計時器實作；測試可注入假時間。 */
  setTimer?: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (t: ReturnType<typeof setTimeout>) => void;
  /** 當下時間（毫秒）；測試可注入單調時鐘。 */
  now?: () => number;
}

export function createNodeAnimator(
  updateStatus: StatusUpdater,
  options: NodeAnimatorOptions = {}
): NodeAnimator {
  const minVisibleMs = options.minVisibleMs ?? MIN_VISIBLE_STATE_MS;
  const setTimer = options.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
  const clearTimer = options.clearTimer ?? ((t) => clearTimeout(t));
  const now = options.now ?? (() => performance.now());

  const queue: Transition[] = [];
  const currentStatus: Record<string, NodeStatus> = {};
  let pendingTimer: ReturnType<typeof setTimeout> | null = null;
  let lastAppliedAt: number = Number.NEGATIVE_INFINITY;

  function pump(): void {
    if (pendingTimer !== null) return;
    const next = queue.shift();
    if (!next) return;

    if (currentStatus[next.nodeId] === next.status) {
      pump();
      return;
    }

    const elapsed = now() - lastAppliedAt;
    const wait = Math.max(0, minVisibleMs - elapsed);

    const apply = () => {
      pendingTimer = null;
      currentStatus[next.nodeId] = next.status;
      lastAppliedAt = now();
      updateStatus(next.nodeId, next.status);
      pump();
    };

    if (wait === 0) {
      apply();
    } else {
      pendingTimer = setTimer(apply, wait);
    }
  }

  return {
    enqueue(nodeId, status) {
      queue.push({ nodeId, status });
      pump();
    },
    reset() {
      if (pendingTimer !== null) {
        clearTimer(pendingTimer);
        pendingTimer = null;
      }
      queue.length = 0;
      for (const k of Object.keys(currentStatus)) delete currentStatus[k];
      lastAppliedAt = Number.NEGATIVE_INFINITY;
    },
  };
}
