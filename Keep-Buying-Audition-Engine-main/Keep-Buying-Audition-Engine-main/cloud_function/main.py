"""
Cloud Function entry: hello_http
─────────────────────────────────────────────
- Runtime: Python 3.12 (Ubuntu 22 Full)
- Entry point: hello_http
- Trigger: HTTP POST application/json
─────────────────────────────────────────────

此檔僅做 HTTP Adapter：解析 request → 呼叫 engine.run_pipeline → 序列化回應 + LINE 推播。
所有 Domain 邏輯位於 engine.py / data.py。LINE 通知函式位於 data.py（唯一來源）。

Request/Response schema 詳見 docs/API_SPEC.md。
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import functions_framework

from data import (
    TPE_TZ, TradingViewSessionExpired, _load_session_meta,
    push_line_message, push_session_expired_alert,
    push_session_expiring_soon_alert, push_error_alert,
)
from engine import ConfigError, run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s %(message)s',
    stream=sys.stdout,
    force=True,
)
for noisy in ('yfinance', 'urllib3', 'requests', 'peewee', 'werkzeug'):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger('hello_http')


# =============================================================================
# LINE 訊息格式化
# =============================================================================
def format_line_message(result, current_holdings: list, start_dt, end_dt) -> str:
    summary = result.to_dict()
    SEP = '─' * 12
    lines = [
        f'📊 {end_dt.strftime("%Y-%m-%d")} 每日建議',
        f'設立日：{start_dt.strftime("%Y-%m-%d")}',
        SEP,
        '【系統績效】',
        f'總報酬  {summary["total_return"]}',
        f'年化    {summary["annualized_return"]}',
        f'最大回撤 {summary["max_drawdown"]}',
        f'Sharpe  {summary["sharpe_ratio"]}',
        f'勝率    {summary["win_rate"]}',
        f'交易    {summary["total_trades"]} 筆',
        SEP,
        '【交易訊號（近3日）】',
    ]
    cutoff = (end_dt - timedelta(days=3)).strftime('%Y-%m-%d')
    recent = [t for t in result.trades if t['date'] >= cutoff]
    if recent:
        for t in recent:
            icon = '🟢' if t['type'] == 'buy' else '🔴'
            action = '買入' if t['type'] == 'buy' else '賣出'
            lines.append(f'{icon} {t["date"][5:]} {action} {t["symbol"]}')
    else:
        lines.append('（無訊號）')
    lines += [SEP, '【現有倉位】']
    if current_holdings:
        for h in sorted(current_holdings, key=lambda x: x['pnl_pct'], reverse=True):
            flag = '🇹🇼' if h.get('country') == 'TW' else '🇺🇸'
            lines.append(f'{flag} {h["symbol"]:<8} {h["pnl_pct"]:+.1%}')
    else:
        lines.append('（無持倉）')
    return '\n'.join(lines)


# =============================================================================
# 錯誤回應
# =============================================================================
_STATUS_MAP = {
    'TRADINGVIEW_SESSION_EXPIRED': 422,
    'CONFIG_ERROR': 400,
    'INVALID_REQUEST': 400,
    'NO_DATA': 422,
    'INTERNAL': 500,
}


def _error_response(
    code: str, message: str, remediation: str = '', details: Optional[dict] = None,
) -> Tuple[dict, int]:
    body = {
        'ok': False,
        'error': {
            'code': code,
            'message': message,
            'remediation': remediation,
            'details': details or {},
        },
    }
    return body, _STATUS_MAP.get(code, 500)


# =============================================================================
# HTTP entry
# =============================================================================
@functions_framework.http
def hello_http(request):
    """Cloud Function HTTP entry。詳見 docs/API_SPEC.md。"""
    if request.method == 'OPTIONS':
        return ('', 204, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600',
        })

    cors_headers = {'Access-Control-Allow-Origin': '*'}
    started = time.perf_counter()

    body = request.get_json(silent=True) or {}

    backtest_params = body.get('backtest') or {}
    if not isinstance(backtest_params, dict):
        resp, status = _error_response('INVALID_REQUEST', 'backtest 必須為物件')
        return (resp, status, cors_headers)

    notify = body.get('notify') or {}
    if not isinstance(notify, dict):
        resp, status = _error_response('INVALID_REQUEST', 'notify 必須為物件')
        return (resp, status, cors_headers)
    line_enabled = bool(notify.get('line', False))

    try:
        ctx = run_pipeline(backtest_params)
    except TradingViewSessionExpired as e:
        push_session_expired_alert(e.expires_at)
        resp, status = _error_response(
            'TRADINGVIEW_SESSION_EXPIRED',
            f'TradingView session 已過期（預計到期日 {e.expires_at}）',
            e.detail,
            details={'expires_at': e.expires_at},
        )
        return (resp, status, cors_headers)
    except ConfigError as e:
        push_error_alert('CONFIG_ERROR', str(e))
        resp, status = _error_response('CONFIG_ERROR', str(e), '請對照 docs/API_SPEC.md 檢查 backtest 欄位')
        return (resp, status, cors_headers)
    except RuntimeError as e:
        push_error_alert('NO_DATA', str(e))
        resp, status = _error_response('NO_DATA', str(e), '請確認 portfolio 內標的代號正確或稍後重試')
        return (resp, status, cors_headers)
    except Exception as e:
        logger.exception('未預期錯誤')
        push_error_alert('INTERNAL', f'{type(e).__name__}: {e}')
        resp, status = _error_response('INTERNAL', f'{type(e).__name__}: {e}', '請查 Cloud Logging 取得 traceback')
        return (resp, status, cors_headers)

    # LINE 推播（僅 Cloud Scheduler 傳 notify.line=true 時觸發）
    notifications: dict = {}
    if line_enabled:
        msg = format_line_message(
            ctx['result'], ctx['current_holdings'], ctx['start_dt'], ctx['end_dt'],
        )
        notifications['line'] = push_line_message(msg)

        # session 到期預警（≤7 天才推，附在每日排程之後）
        expires_at, _, _ = _load_session_meta()
        push_session_expiring_soon_alert(expires_at)

    response = {
        'ok': True,
        'result': ctx['result'].to_dict(),
        'equity_curve': ctx['result'].equity_curve,
        'benchmark_curve': ctx['benchmark_curve'],
        'benchmark_name': ctx['benchmark_name'],
        'trades': ctx['result'].trades,
        'holdings': ctx['current_holdings'],
        'meta': {
            'timestamp': datetime.now(TPE_TZ).isoformat(timespec='seconds'),
            'execution_time_ms': int((time.perf_counter() - started) * 1000),
            'portfolio_source': ctx['portfolio_source'],
            'symbols_count': ctx['symbols_count'],
            'data_range': [
                ctx['start_dt'].strftime('%Y-%m-%d'),
                ctx['end_dt'].strftime('%Y-%m-%d'),
            ],
        },
        'notifications': notifications,
    }
    return (response, 200, cors_headers)
