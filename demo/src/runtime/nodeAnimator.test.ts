/**
 * nodeAnimator 嚴格序列契約測試。
 *
 * 目標:把後端可能的事件抵達 pattern 拆成 4 種情境,逐一驗證使用者
 * 看到的視覺敘事符合規格:
 *   - perceive 黃 → perceive 綠 → plan 黃 → plan 綠 → ...
 *   - 同一時刻最多一個節點處於「最新 transition」
 *   - 每個 status 在被下一個 transition 覆蓋前至少存活 minVisibleMs
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createNodeAnimator, MIN_VISIBLE_STATE_MS } from "./nodeAnimator";
import type { NodeStatus } from "./types";

/** 收集所有 updateStatus 呼叫,連同當下假時間。 */
function makeRecorder() {
  const calls: Array<{ t: number; nodeId: string; status: NodeStatus }> = [];
  return {
    calls,
    update: (nodeId: string, status: NodeStatus) => {
      calls.push({ t: Date.now(), nodeId, status });
    },
  };
}

describe("nodeAnimator 嚴格序列", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  /** 把 vi 假時鐘整合進 animator(now=Date.now,setTimer=setTimeout)。 */
  function build(minVisibleMs = MIN_VISIBLE_STATE_MS) {
    const rec = makeRecorder();
    const animator = createNodeAnimator(rec.update, {
      minVisibleMs,
      now: () => Date.now(),
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (t) => clearTimeout(t),
    });
    return { rec, animator };
  }

  it("情境 A:單一節點的 running → ok 必呈現兩次 transition,間隔不小於 minVisibleMs", () => {
    const { rec, animator } = build(300);

    animator.enqueue("perceive", "running");
    animator.enqueue("perceive", "ok");

    // 同 tick 應立即 apply running(lastAppliedAt 是 -Infinity)
    expect(rec.calls).toEqual([{ t: 0, nodeId: "perceive", status: "running" }]);

    // 200ms 還不到 minVisibleMs,ok 仍未 apply
    vi.advanceTimersByTime(200);
    expect(rec.calls).toHaveLength(1);

    // 推到 300ms,timer 觸發 ok
    vi.advanceTimersByTime(100);
    expect(rec.calls).toEqual([
      { t: 0, nodeId: "perceive", status: "running" },
      { t: 300, nodeId: "perceive", status: "ok" },
    ]);
  });

  it("情境 B:後端 buffer 一次 flush 6 個事件(模擬 Cloud Run cold start 後爆量),仍以嚴格序列輸出", () => {
    const { rec, animator } = build(100);

    // 模擬 SSE 在 t=0 抵達 perceive.start / perceive.finish / plan.start / plan.finish / action.start / action.finish
    animator.enqueue("perceive", "running");
    animator.enqueue("perceive", "ok");
    animator.enqueue("plan", "running");
    animator.enqueue("plan", "ok");
    animator.enqueue("action", "running");
    animator.enqueue("action", "ok");

    // 第一個立即輸出
    expect(rec.calls).toHaveLength(1);

    // 推進到佇列清空(預期 6 個 transition × 100ms = 至少 500ms)
    vi.advanceTimersByTime(700);

    expect(rec.calls).toEqual([
      { t: 0,   nodeId: "perceive", status: "running" },
      { t: 100, nodeId: "perceive", status: "ok" },
      { t: 200, nodeId: "plan",     status: "running" },
      { t: 300, nodeId: "plan",     status: "ok" },
      { t: 400, nodeId: "action",   status: "running" },
      { t: 500, nodeId: "action",   status: "ok" },
    ]);
  });

  it("情境 C:慢節點(Plan LLM 20s)yellow 延伸到 ok 真實抵達時才綠", () => {
    const { rec, animator } = build(100);

    animator.enqueue("perceive", "running");
    animator.enqueue("perceive", "ok");
    animator.enqueue("plan", "running");

    // 推進到 plan.running 已 apply(perceive 兩個 transition + plan running = 至少 200ms)
    vi.advanceTimersByTime(300);
    expect(rec.calls.map((c) => c.status)).toEqual(["running", "ok", "running"]);
    expect(rec.calls[2].nodeId).toBe("plan");

    // 模擬 LLM 跑 20 秒,期間沒有任何新 enqueue
    vi.advanceTimersByTime(20000);

    // 還是只有 3 筆,plan 仍是 running
    expect(rec.calls).toHaveLength(3);

    // 此刻 LLM 完成,enqueue plan.ok + action.running
    animator.enqueue("plan", "ok");
    animator.enqueue("action", "running");

    // 上一個 apply 在 t=200,現在 t=20300,elapsed 早已超過 100ms,所以 plan.ok 立即 apply
    expect(rec.calls).toHaveLength(4);
    expect(rec.calls[3]).toMatchObject({ nodeId: "plan", status: "ok", t: 20300 });

    // action.running 排隊中,需等 minVisibleMs
    vi.advanceTimersByTime(100);
    expect(rec.calls[4]).toMatchObject({ nodeId: "action", status: "running", t: 20400 });
  });

  it("情境 D:重複 status 自動 dedupe(SSE 重送或樂觀更新撞到 backend 真實事件)", () => {
    const { rec, animator } = build(100);

    animator.enqueue("perceive", "running");
    animator.enqueue("perceive", "running"); // 重送
    animator.enqueue("perceive", "running"); // 樂觀後又收到 backend
    animator.enqueue("perceive", "ok");

    vi.advanceTimersByTime(200);

    expect(rec.calls).toEqual([
      { t: 0, nodeId: "perceive", status: "running" },
      { t: 100, nodeId: "perceive", status: "ok" },
    ]);
  });

  it("情境 E:reset 清空佇列與計時器,下一個 enqueue 立即 apply", () => {
    const { rec, animator } = build(100);

    animator.enqueue("perceive", "running");
    animator.enqueue("perceive", "ok");
    animator.enqueue("plan", "running");

    vi.advanceTimersByTime(50);
    // 此時 perceive.ok 還在 timer 排程中
    expect(rec.calls).toHaveLength(1);

    animator.reset();

    // 推進大量時間,reset 之前排程的 timer 不應該再 fire
    vi.advanceTimersByTime(10000);
    expect(rec.calls).toHaveLength(1);

    // 新一輪 enqueue,因為 lastAppliedAt 被重設為 -Infinity,立即 apply
    animator.enqueue("perceive", "running");
    expect(rec.calls).toHaveLength(2);
    expect(rec.calls[1]).toMatchObject({ nodeId: "perceive", status: "running" });
  });

  it("情境 F:Plan → Retrieve → Plan → Action 的非線性路由,黃綠順序與 enqueue 順序一致", () => {
    const { rec, animator } = build(100);

    const events: Array<[string, NodeStatus]> = [
      ["perceive", "running"],
      ["perceive", "ok"],
      ["plan", "running"],
      ["plan", "ok"],
      ["retrieve", "running"],
      ["retrieve", "ok"],
      ["plan", "running"], // 第二次回到 plan
      ["plan", "ok"],
      ["action", "running"],
      ["action", "ok"],
    ];
    events.forEach(([n, s]) => animator.enqueue(n, s));

    vi.advanceTimersByTime(2000);

    expect(rec.calls.map((c) => [c.nodeId, c.status])).toEqual(events);
    // 每兩個相鄰 transition 之間間距 ≥ 100ms
    for (let i = 1; i < rec.calls.length; i++) {
      expect(rec.calls[i].t - rec.calls[i - 1].t).toBeGreaterThanOrEqual(100);
    }
  });

  it("情境 G:任意時刻(以 enqueue 後的所有狀態 snapshot 來看)同時只能有一個節點處於『最新 running』", () => {
    const { rec, animator } = build(100);

    animator.enqueue("perceive", "running");
    animator.enqueue("perceive", "ok");
    animator.enqueue("plan", "running");
    animator.enqueue("plan", "ok");
    animator.enqueue("action", "running");

    vi.advanceTimersByTime(2000);

    // 重建每個 transition 後的全節點狀態,驗證任何時間點都只有 0 或 1 個 running
    const state: Record<string, NodeStatus> = {};
    for (const c of rec.calls) {
      state[c.nodeId] = c.status;
      const runningCount = Object.values(state).filter((s) => s === "running").length;
      expect(runningCount).toBeLessThanOrEqual(1);
    }
  });
});
