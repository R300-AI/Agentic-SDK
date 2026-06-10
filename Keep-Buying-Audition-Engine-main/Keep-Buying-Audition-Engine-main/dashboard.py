"""
Dashboard (WebUI Adapter)
─────────────────────────────────────────────
本地 demo：表單 → 直接 import engine.run_pipeline → JSON → 前端 Chart.js 繪圖。
入口位於根目錄；templates / static 資產位於 webui/。

啟動：
    python dashboard.py
    瀏覽器開 http://127.0.0.1:5000
"""
from __future__ import annotations

import logging
import sys
import time
import traceback
import yaml
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'cloud_function'))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from data import (  # noqa: E402
    TradingViewSessionExpired, TPE_TZ,
    push_session_expired_alert,
)
from engine import ConfigError, run_pipeline  # noqa: E402

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
for noisy in ('yfinance', 'urllib3', 'requests', 'peewee'):
    logging.getLogger(noisy).setLevel(logging.WARNING)
# werkzeug 保留 INFO → 顯示每筆 HTTP 請求記錄，滿足可觀察性原則

logger = logging.getLogger('dashboard')

CONFIG_YAML = ROOT / 'cloud_function' / 'config.yaml'

_STATUS_MAP = {
    'TRADINGVIEW_SESSION_EXPIRED': 422,
    'CONFIG_ERROR': 400,
    'INVALID_REQUEST': 400,
    'NO_DATA': 422,
    'INTERNAL': 500,
}


app = Flask(
    __name__,
    template_folder=str(ROOT / 'webui' / 'templates'),
    static_folder=str(ROOT / 'webui' / 'static'),
)


@app.after_request
def _log_request(response):
    """所有 HTTP 請求統一在此記錄，確保可觀察性。"""
    logger.info('%s %s → %d', request.method, request.path, response.status_code)
    return response


def _err(code: str, message: str, remediation: str = '', details: dict | None = None):
    return jsonify({
        'ok': False,
        'error': {'code': code, 'message': message, 'remediation': remediation, 'details': details or {}},
    }), _STATUS_MAP.get(code, 500)


@app.route('/')
def index():
    logger.info('GET / → render index.html')
    return render_template('index.html')


@app.get('/api/config')
def api_get_config():
    logger.info('GET /api/config')
    try:
        with open(CONFIG_YAML, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error('讀取 config.yaml 失敗: %s', e)
        return _err('INTERNAL', f'無法讀取 config.yaml: {e}')
    logger.info('config.yaml 讀取成功（tradingview.session_id=%s…）',
                str(cfg.get('tradingview', {}).get('session_id', ''))[:8])
    return jsonify({'ok': True, 'config': cfg})


@app.post('/api/config')
def api_save_config():
    body = request.get_json(silent=True) or {}
    sections = [k for k in ('tradingview', 'line', 'backtest') if k in body]
    logger.info('POST /api/config → 更新區段: %s', sections)
    try:
        with open(CONFIG_YAML, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error('讀取 config.yaml 失敗: %s', e)
        return _err('INTERNAL', f'無法讀取 config.yaml: {e}')

    for section in ('tradingview', 'line'):
        if section in body:
            cfg[section] = body[section]
    if 'backtest' in body:
        bt = cfg.setdefault('backtest', {})
        for k, v in body['backtest'].items():
            # buy_conditions / sell_conditions / rebalance_strategy 做 per-key 合併，避免覆蓋整個子結構
            if isinstance(bt.get(k), dict) and isinstance(v, dict):
                bt[k] = {**bt[k], **v}
            else:
                bt[k] = v

    try:
        with open(CONFIG_YAML, 'w', encoding='utf-8') as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.error('寫入 config.yaml 失敗: %s', e)
        return _err('INTERNAL', f'無法寫入 config.yaml: {e}')
    logger.info('config.yaml 寫入成功')
    return jsonify({'ok': True})


@app.post('/api/backtest')
def api_backtest():
    started = time.perf_counter()
    body = request.get_json(silent=True) or {}
    logger.info('POST /api/backtest → params=%s', body.get('backtest', {}))

    backtest_params = body.get('backtest') or {}
    if not isinstance(backtest_params, dict):
        return _err('INVALID_REQUEST', 'backtest 必須為物件')

    try:
        ctx = run_pipeline(backtest_params)
    except TradingViewSessionExpired as e:
        push_session_expired_alert(e.expires_at)
        return _err('TRADINGVIEW_SESSION_EXPIRED',
                    f'TradingView session 已過期（預計到期日 {e.expires_at}）',
                    remediation=e.detail, details={'expires_at': e.expires_at})
    except ConfigError as e:
        logger.warning('CONFIG_ERROR: %s', e)
        return _err('CONFIG_ERROR', str(e))
    except RuntimeError as e:
        logger.exception('NO_DATA: %s', e)
        return _err('NO_DATA', str(e))
    except Exception as e:
        logger.exception('未預期錯誤')
        return _err('INTERNAL', f'{type(e).__name__}: {e}',
                    details={'traceback': traceback.format_exc()})

    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info('回測完成 → symbols=%d  elapsed=%dms',
                ctx['symbols_count'], elapsed)
    # dashboard 是本地工具，不推 LINE（避免 WebUI 測試時誤發通知）
    return jsonify({
        'ok': True,
        'result': ctx['result'].to_dict(),
        'equity_curve': ctx['result'].equity_curve,
        'benchmark_curve': ctx['benchmark_curve'],
        'benchmark_name': ctx['benchmark_name'],
        'trades': ctx['result'].trades,
        'holdings': ctx['current_holdings'],
        'meta': {
            'timestamp': datetime.now(TPE_TZ).isoformat(timespec='seconds'),
            'execution_time_ms': elapsed,
            'portfolio_source': ctx['portfolio_source'],
            'symbols_count': ctx['symbols_count'],
            'data_range': [
                ctx['start_dt'].strftime('%Y-%m-%d'),
                ctx['end_dt'].strftime('%Y-%m-%d'),
            ],
        },
        'notifications': {},
    })


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
