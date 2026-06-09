"""scripts/demo_multi_backend.py — 多基台端到端驗收(M4-1~M4-3)。

執行情境:
    在 Ryzen 機台上跑 amd-ryzen-ai-benchmark 的 `python api.py --model gemma3-...`,
    本腳本同時驗證:
      1. Action 走 Ryzen Gemma3 上游(走 UpstreamCompletionAction)
      2. Action 走 Azure Foundry deployment(走 FoundryCompletionAction)
      3. 同一份 WorkflowConfig 拓樸,只換 node_overrides 即可切 backend

使用方式:
    # 環境變數(於 Ryzen 機器):
    #   RYZEN_UPSTREAM_BASE_URL   預設 http://127.0.0.1:8000/v1
    #   RYZEN_MODEL               預設 gemma-3-4b-it
    #   AZURE_FOUNDRY_ENDPOINT    必填(.env 內已有則自動讀)
    #   AZURE_FOUNDRY_API_KEY     必填
    #   AZURE_FOUNDRY_DEPLOYMENT  預設 gpt-4o-mini

    uv run python scripts/demo_multi_backend.py

輸出:
    1) docs/quickstart-runs/multi-backend-<timestamp>.json — 結構化結果
    2) stdout 摘要(成功/失敗、各 backend 回應、context entry 序列)
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


def _preflight_ryzen(base_url: str, model: str) -> None:
    """GET /v1/models 確認 Ryzen 端點存活,且目標 model 已載入。

    若端點不通 → 拋 RuntimeError。
    若 /v1/models 不支援(4xx)→ 靜默略過。
    若 model 不在清單 → 拋 RuntimeError 並列出可用清單,方便核對 --model 參數。
    """
    import json as _json
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = _json.loads(resp.read())
        available = [m.get("id", "") for m in data.get("data", [])]
        if available and model not in available:
            raise RuntimeError(
                f"Ryzen 端點有回應,但 model '{model}' 不在可用清單中。\n"
                f"可用 models: {available}\n"
                f"請確認 api.py --model 參數與 RYZEN_MODEL 是否一致。"
            )
        print(f"[demo_multi_backend] ryzen preflight OK — models: {available or '(api 未列出)'}")
    except urllib.error.HTTPError:
        # GET /v1/models 返回 4xx → 端點不支援此 endpoint,略過 preflight
        pass
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ryzen 端點 {base_url} 無法連線: {exc.reason}") from exc


def _run_ryzen_action(prompt: str, base_url: str, model: str) -> dict:
    # Preflight: 確認 Ryzen 端點存活且 model 已載入(失敗就快速失敗,不浪費 3 次重試)
    _preflight_ryzen(base_url, model)

    from agentic_sdk.context import ContextEntryType
    from agentic_sdk.config import Settings
    from agentic_sdk.workflow import GateConfig, NodeSpec, Workflow, WorkflowConfig
    from agentic_sdk.workflow.nodes.action import UpstreamCompletionAction

    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        upstream_api_base_url=base_url,
        upstream_api_key=os.environ.get("UPSTREAM_API_KEY", "not-needed"),
        infer_request_timeout_sec=float(os.environ.get("INFER_REQUEST_TIMEOUT_SEC", "60")),
        workflow_force_mock_foundry=True,
        workflow_action_backend="upstream",
        azure_foundry_endpoint=os.environ.get("AZURE_FOUNDRY_ENDPOINT", "https://placeholder.example.com/"),
        azure_foundry_api_key=os.environ.get("AZURE_FOUNDRY_API_KEY", "placeholder"),
    )
    action = UpstreamCompletionAction(settings=s, model=model)
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="upstream_completion", params={"model": model})},
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=60.0),
    )
    wf = Workflow.from_config(config, settings=s, node_overrides={"action": action})

    t0 = time.monotonic()
    result = wf.run(prompt)
    elapsed = time.monotonic() - t0

    # 從 context entries 找最後一個 action 失敗的錯誤訊息,補充 abort_reason 之外的細節
    last_action_error: str | None = None
    for entry in reversed(result.entries):
        if (
            entry.type == ContextEntryType.ACTION_RESULT
            and not entry.metadata.get("ok", True)
        ):
            last_action_error = entry.metadata.get("error")
            break

    return {
        "backend": "ryzen_upstream",
        "base_url": base_url,
        "model": model,
        "ok": not result.aborted,
        "elapsed_sec": round(elapsed, 3),
        "final_message": result.final_message,
        "abort_reason": result.abort_reason,
        "last_action_error": last_action_error,
        "entry_types": [e.type.value for e in result.entries],
        "visit_counts": dict(result.visit_counts),
    }


def _run_foundry_action(prompt: str) -> dict:
    # 在讀取 env 前先確認必填項目已設,給出明確錯誤訊息而非 KeyError
    _endpoint = os.environ.get("AZURE_FOUNDRY_ENDPOINT")
    _api_key = os.environ.get("AZURE_FOUNDRY_API_KEY")
    if not _endpoint or not _api_key:
        missing = [
            k for k, v in [("AZURE_FOUNDRY_ENDPOINT", _endpoint), ("AZURE_FOUNDRY_API_KEY", _api_key)]
            if not v
        ]
        raise EnvironmentError(
            f".env 缺少必填項目: {', '.join(missing)}。"
            f"請複製 .env.example 並填入 Azure Foundry 憑證後重跑。"
        )

    from agentic_sdk.config import Settings
    from agentic_sdk.workflow import GateConfig, NodeSpec, Workflow, WorkflowConfig
    from agentic_sdk.workflow.nodes.action import FoundryCompletionAction

    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        workflow_force_mock_foundry=True,
        workflow_action_backend="foundry",
        azure_foundry_endpoint=_endpoint,
        azure_foundry_api_key=_api_key,
        azure_foundry_deployment=os.environ.get("AZURE_FOUNDRY_DEPLOYMENT", "gpt-4o-mini"),
        upstream_api_base_url="http://placeholder:8000/v1",
        infer_request_timeout_sec=float(os.environ.get("INFER_REQUEST_TIMEOUT_SEC", "60")),
    )
    action = FoundryCompletionAction(settings=s)
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="foundry_completion")},
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=60.0),
    )
    wf = Workflow.from_config(config, settings=s, node_overrides={"action": action})

    t0 = time.monotonic()
    result = wf.run(prompt)
    elapsed = time.monotonic() - t0

    return {
        "backend": "azure_foundry",
        "deployment": s.azure_foundry_deployment,
        "endpoint": s.azure_foundry_endpoint,
        "ok": not result.aborted,
        "elapsed_sec": round(elapsed, 3),
        "final_message": result.final_message,
        "abort_reason": result.abort_reason,
        "entry_types": [e.type.value for e in result.entries],
        "visit_counts": dict(result.visit_counts),
    }


def _safe_run(name: str, fn, *args) -> dict:
    try:
        return fn(*args)
    except Exception as exc:
        return {
            "backend": name,
            "ok": False,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }


def main(argv: list[str]) -> int:
    # Windows PowerShell 5.1 預設 codepage 可能讓中文 CLI 引數變亂碼;
    # 對 argv[1] 走一次「以當前 stdin 編碼解回 bytes 再以 UTF-8 解碼」嘗試,
    # 失敗就維持原值(英文 / Linux 環境本來就沒事)。
    raw = argv[1] if len(argv) > 1 else "請用一句話自我介紹"
    try:
        prompt = raw.encode(sys.stdin.encoding or "utf-8", errors="strict").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        prompt = raw
    ryzen_base = os.environ.get("RYZEN_UPSTREAM_BASE_URL", "http://127.0.0.1:8000/v1")
    ryzen_model = os.environ.get("RYZEN_MODEL", "gemma-3-4b-it")

    print(f"[demo_multi_backend] prompt = {prompt!r}")
    print(f"[demo_multi_backend] ryzen_base = {ryzen_base}")
    print(f"[demo_multi_backend] ryzen_model = {ryzen_model}")

    ryzen_result = _safe_run("ryzen_upstream", _run_ryzen_action, prompt, ryzen_base, ryzen_model)
    foundry_result = _safe_run("azure_foundry", _run_foundry_action, prompt)

    report = {
        "schema": "multi-backend-run/1",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "results": [ryzen_result, foundry_result],
        "summary": {
            "ryzen_ok": ryzen_result.get("ok", False),
            "foundry_ok": foundry_result.get("ok", False),
            "both_ok": ryzen_result.get("ok", False) and foundry_result.get("ok", False),
        },
    }

    out_dir = Path(__file__).resolve().parent.parent / "docs" / "quickstart-runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"multi-backend-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("─" * 60)
    print(f"  Ryzen    backend  : {'OK' if ryzen_result.get('ok') else 'FAIL'}")
    if ryzen_result.get("ok"):
        print(f"           reply   : {ryzen_result['final_message']!r}")
        print(f"           elapsed : {ryzen_result['elapsed_sec']} s")
    else:
        if ryzen_result.get("error_type"):
            print(f"           error   : {ryzen_result.get('error_type')}: {ryzen_result.get('error_message')}")
        if ryzen_result.get("last_action_error"):
            print(f"           upstream: {ryzen_result.get('last_action_error')}")
        if ryzen_result.get("abort_reason"):
            print(f"           abort   : {ryzen_result.get('abort_reason')}")

    print()
    print(f"  Foundry  backend  : {'OK' if foundry_result.get('ok') else 'FAIL'}")
    if foundry_result.get("ok"):
        print(f"           reply   : {foundry_result['final_message']!r}")
        print(f"           elapsed : {foundry_result['elapsed_sec']} s")
    else:
        if foundry_result.get("error_type"):
            print(f"           error   : {foundry_result.get('error_type')}: {foundry_result.get('error_message')}")
        if foundry_result.get("abort_reason"):
            print(f"           abort   : {foundry_result.get('abort_reason')}")

    print("─" * 60)
    print(f"  report saved   -> {out_path.relative_to(Path.cwd()) if out_path.is_relative_to(Path.cwd()) else out_path}")
    print(f"  both backends  : {'OK' if report['summary']['both_ok'] else 'PARTIAL / FAIL'}")
    print("─" * 60)

    return 0 if report["summary"]["both_ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
