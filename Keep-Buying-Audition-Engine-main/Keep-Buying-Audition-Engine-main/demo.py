"""
GCF 端點驗證客戶端
─────────────────────────────────────────────
對已部署的 Cloud Function 發送 HTTP 請求，驗證端點是否正常運作。
本檔不 import 任何 cloud_function/ 模組，是純粹的 HTTP 客戶端。

用法：
    uv run demo.py --url https://<GCF_URL>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

import requests


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Portfolio Optimizer GCF 驗證客戶端')
    p.add_argument('--url', required=True, help='GCF HTTP 觸發 URL')
    p.add_argument('--notify-line', action='store_true',
                   help='測試 LINE 推播（預設關閉，避免誤推）')
    p.add_argument('--timeout', type=int, default=300, help='請求逾時秒數（預設 300）')
    return p.parse_args()


def _build_payload(args: argparse.Namespace) -> dict:
    return {'notify': {'line': args.notify_line}}


def _print_result(data: dict) -> None:
    if not data.get('ok'):
        err = data.get('error', {})
        print(f'\n[失敗] {err.get("code")}: {err.get("message")}')
        if err.get('remediation'):
            print(f'  → {err["remediation"]}')
        return

    result = data.get('result', {})
    meta = data.get('meta', {})
    holdings = data.get('holdings', [])
    trades = data.get('trades', [])
    benchmark_name = data.get('benchmark_name', 'N/A')
    benchmark_curve = data.get('benchmark_curve', [])

    print('\n' + '=' * 60)
    print('Portfolio Optimizer GCF — 回測結果')
    print('=' * 60)
    print(f"  投資組合來源 : {meta.get('portfolio_source')}")
    print(f"  市場         : {result.get('market', 'N/A')}")
    print(f"  回測期間     : {meta.get('data_range', ['?', '?'])[0]} → {meta.get('data_range', ['?', '?'])[1]}")
    print(f"  執行時間     : {meta.get('execution_time_ms')} ms")
    print('-' * 60)
    print(f"  初始資金     : {result.get('initial_capital')}")
    print(f"  最終資產     : {result.get('final_equity')}")
    print(f"  總報酬率     : {result.get('total_return')}")
    print(f"  年化報酬率   : {result.get('annualized_return')}")
    print(f"  Sharpe Ratio : {result.get('sharpe_ratio')}")
    print(f"  最大回撤     : {result.get('max_drawdown')}")
    print(f"  勝率         : {result.get('win_rate')}  ({result.get('win_trades')}/{result.get('total_trades')})")
    if benchmark_curve:
        print(f"  基準（{benchmark_name}）終值: {benchmark_curve[-1].get('equity', 'N/A'):.0f} TWD")
    print('-' * 60)
    print(f"  當前持倉（{len(holdings)} 檔）")
    for h in holdings[:10]:
        pnl = h.get('pnl_pct', 0) * 100
        print(f"    {h.get('symbol'):<12} {h.get('shares', 0):>6}"
              f"  市值 {h.get('market_value_twd', 0):>12,.0f} TWD  PnL {pnl:+6.2f}%")
    if len(holdings) > 10:
        print(f"    ... 其餘 {len(holdings) - 10} 檔省略")
    print('-' * 60)
    recent = trades[-5:] if trades else []
    print(f"  最近 5 筆交易（共 {len(trades)} 筆）")
    for t in recent:
        print(f"    {t.get('date')}  {t.get('type'):<4}  {t.get('symbol'):<12}")

    notifications = data.get('notifications', {})
    if notifications.get('line'):
        line_status = notifications['line']
        status_str = '已送出' if line_status.get('sent') else f"未送出（{line_status.get('reason')}）"
        print(f"  LINE 推播    : {status_str}")
    print('=' * 60)


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(message)s')
    args = _parse_args()
    payload = _build_payload(args)

    print(f'呼叫 GCF: {args.url}')
    print(f'Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}')

    started = time.perf_counter()
    try:
        resp = requests.post(
            args.url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=args.timeout,
        )
    except requests.exceptions.Timeout:
        print(f'\n[錯誤] 請求逾時（{args.timeout} 秒）')
        return 1
    except requests.exceptions.ConnectionError as e:
        print(f'\n[錯誤] 無法連線至 GCF: {e}')
        return 1

    elapsed = time.perf_counter() - started
    print(f'HTTP {resp.status_code}  ({elapsed:.1f}s)')

    try:
        data = resp.json()
    except Exception:
        print(f'[錯誤] 回應非 JSON:\n{resp.text[:500]}')
        return 1

    _print_result(data)
    return 0 if data.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())

