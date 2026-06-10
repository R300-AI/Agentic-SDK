"""
資料層：TradingView watchlist、yfinance 股價、日期對齊、幣別、匯率。

設計原則：
- 純函數，無檔案系統依賴（無 BASE_DIR）
- TradingView session 過期透過 TradingViewSessionExpired 例外向上傳遞
- 所有外部憑證與策略參數存於 cloud_function/config.yaml，不使用環境變數
- 本地開發模式支援日期對齊的 pickle 快取（同一天不重新拗取 yfinance）
  快取目錄：{project_root}/.cache/   （不上傳 GCF）
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd
import requests
import yaml
import yfinance as yf

logger = logging.getLogger(__name__)

# =============================================================================
# 常數
# =============================================================================
SHARPE_WINDOW = 252
RISK_FREE_RATE = 0.04
DATA_PERIOD = '6y'
MIN_HISTORY_DAYS = 100
MIN_STOCKS_FOR_VALID_DAY = 50
MIN_STOCKS_FOR_VALID_DAY_RATIO = 0.5
NON_TRADABLE_INDUSTRIES = frozenset({'Market Index', 'Index'})

CONFIG_FILE = Path(__file__).parent / 'config.yaml'
TPE_TZ = timezone(timedelta(hours=8))

# 快取目錄： cloud_function/ 的上層 .cache/（不上傳 GCF）
_CACHE_DIR = Path(__file__).parent.parent / '.cache'


# =============================================================================
# 本地快取工具（僅在檔案系統存在時使用，GCF 上異常會被 catch 略過）
# =============================================================================
def _cache_path(key: str) -> Path:
    """key 加上今日日期作為快取路徑，每天自動失效。"""
    today = date.today().isoformat()          # e.g. 2026-06-07
    safe_key = key.replace('/', '_').replace(':', '_')
    return _CACHE_DIR / f'{safe_key}__{today}.pkl'


def _load_cache(key: str):
    """\u8b80取快取。不存在、過期、任何錯誤均回傳 None。"""
    try:
        p = _cache_path(key)
        if p.exists():
            data = pickle.loads(p.read_bytes())  # noqa: S301 本地己寫己讀，安全
            logger.debug('[cache hit] %s', key)
            return data
    except Exception as e:
        logger.debug('[cache read error] %s: %s', key, e)
    return None


def _save_cache(key: str, data) -> None:
    """\u5beb入快取。建立目錄失敗時靜默略過（GCF 等無權限環境）。"""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_bytes(pickle.dumps(data))
        logger.debug('[cache saved] %s', key)
    except Exception as e:
        logger.debug('[cache write error] %s: %s', key, e)


# =============================================================================
# 例外
# =============================================================================
class TradingViewSessionExpired(RuntimeError):
    """TradingView sessionid cookie 已過期或無效。"""

    def __init__(self, expires_at: Optional[str], detail: str):
        self.expires_at = expires_at
        self.detail = detail
        super().__init__(detail)


# =============================================================================
# 幣別與 Money
# =============================================================================
class Currency(Enum):
    TWD = 'TWD'
    USD = 'USD'

    def __str__(self) -> str:
        return self.value


class CurrencyMismatchError(TypeError):
    def __init__(self, left: Currency, right: Currency, op: str):
        super().__init__(f'幣別不匹配: {left} {op} {right}')


@dataclass
class Money:
    amount: float
    currency: Currency

    def __post_init__(self):
        if isinstance(self.currency, str):
            object.__setattr__(self, 'currency', Currency(self.currency.upper()))

    def __add__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency, '+')
        return Money(self.amount + other.amount, self.currency)

    def __radd__(self, other):
        if other == 0:
            return self
        return self.__add__(other)

    def __sub__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency, '-')
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, n):
        if isinstance(n, Money):
            raise TypeError('Money 不能與 Money 相乘')
        return Money(self.amount * n, self.currency)

    def __rmul__(self, n):
        return self.__mul__(n)

    def __truediv__(self, other):
        if isinstance(other, Money):
            if self.currency != other.currency:
                raise CurrencyMismatchError(self.currency, other.currency, '/')
            return self.amount / other.amount
        return Money(self.amount / other, self.currency)

    def __eq__(self, other):
        if not isinstance(other, Money):
            return False
        return self.currency == other.currency and abs(self.amount - other.amount) < 1e-6

    def __lt__(self, other):
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency, '<')
        return self.amount < other.amount

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency, '>')
        return self.amount > other.amount

    def __ge__(self, other):
        return self == other or self > other

    def __neg__(self):
        return Money(-self.amount, self.currency)

    def __bool__(self):
        return self.amount != 0

    def __hash__(self):
        return hash((round(self.amount, 6), self.currency))

    def __str__(self):
        if self.currency == Currency.TWD:
            return f'${self.amount:,.0f} TWD'
        return f'${self.amount:,.2f} USD'

    def is_twd(self) -> bool:
        return self.currency == Currency.TWD

    def is_usd(self) -> bool:
        return self.currency == Currency.USD


def twd(amount: float) -> Money:
    return Money(amount, Currency.TWD)


def usd(amount: float) -> Money:
    return Money(amount, Currency.USD)


# =============================================================================
# 匯率服務（USD/TWD）
# =============================================================================
class FX:
    DEFAULT_RATE = 32.0

    def __init__(self):
        self._history: Dict[str, float] = {}
        self._latest = self.DEFAULT_RATE
        self._fetch_from_yfinance()

    def _fetch_from_yfinance(self):
        cache_key = 'fx__TWDUSD__6y'
        cached = _load_cache(cache_key)
        if cached is not None:
            self._history = cached['history']
            self._latest  = cached['latest']
            return
        try:
            df = yf.Ticker('TWD=X').history(period='6y', interval='1d')
            if df.empty:
                return
            self._history = {
                d.strftime('%Y-%m-%d'): round(float(r['Close']), 4)
                for d, r in df.iterrows() if pd.notna(r.get('Close'))
            }
            if self._history:
                self._latest = self._history[max(self._history.keys())]
            _save_cache(cache_key, {'history': self._history, 'latest': self._latest})
        except Exception as e:
            logger.warning('FX 抓取失敗，使用預設匯率 %.2f: %s', self.DEFAULT_RATE, e)

    def rate(self, date_str: Optional[str] = None) -> float:
        if date_str is None:
            return self._latest
        if date_str in self._history:
            return self._history[date_str]
        if self._history:
            for d in reversed(sorted(self._history.keys())):
                if d <= date_str:
                    return self._history[d]
        return self.DEFAULT_RATE

    def to_twd(self, m: Money, date_str: Optional[str] = None) -> Money:
        if m.is_twd():
            return m
        return twd(m.amount * self.rate(date_str))

    def to_usd(self, m: Money, date_str: Optional[str] = None) -> Money:
        if m.is_usd():
            return m
        return usd(m.amount / self.rate(date_str))


# =============================================================================
# TradingView Session 過期偵測
# =============================================================================
def _load_session_meta() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """讀取 config.yaml，回傳 (expires_at, session_id, watchlist_id)。"""
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            meta = yaml.safe_load(f) or {}
        tv = meta.get('tradingview', {})
        return (
            tv.get('expires_at'),
            tv.get('session_id') or None,
            tv.get('watchlist_id') or None,
        )
    except Exception as e:
        logger.warning('無法讀取 %s: %s', CONFIG_FILE, e)
        return None, None, None


def _is_session_likely_expired(expires_at: Optional[str]) -> bool:
    """判斷 sessionid 是否可能已過期（今日 >= 預計過期日）。"""
    if not expires_at:
        return True
    try:
        return date.today() >= datetime.strptime(expires_at, '%Y-%m-%d').date()
    except ValueError:
        return True


def _build_session_expired_error(expires_at: Optional[str] = None) -> TradingViewSessionExpired:
    if expires_at is None:
        expires_at, _, _ = _load_session_meta()
    remediation = (
        '請至 https://www.tradingview.com 重新登入，'
        '從瀏覽器 DevTools 取得 sessionid cookie，'
        '將新值填入 cloud_function/config.yaml 的 tradingview.session_id 欄位，'
        '並同步將 expires_at 改為新 cookie 的預計到期日（+30 天）。'
    )
    return TradingViewSessionExpired(
        expires_at=expires_at,
        detail=remediation,
    )


# =============================================================================
# TradingView Watchlist
# =============================================================================
def fetch_watchlist() -> Tuple[Dict, Dict]:
    """
    從 TradingView 取得投資組合清單。

    Raises:
        TradingViewSessionExpired: sessionid 過期或被擋
        RuntimeError: 缺少環境變數

    Returns:
        (watchlist, stock_info)
    """
    expires_at, session_id, watchlist_id = _load_session_meta()
    if not session_id:
        raise RuntimeError(
            '設定缺少 TradingView session_id：'
            '請填入 cloud_function/config.yaml 的 tradingview.session_id 欄位'
        )
    if not watchlist_id:
        raise RuntimeError(
            '設定缺少 TradingView watchlist_id：'
            '請填入 cloud_function/config.yaml 的 tradingview.watchlist_id 欄位'
        )

    url = f'https://in.tradingview.com/api/v1/symbols_list/custom/{watchlist_id}'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'cookie': f'sessionid={session_id}',
        'x-requested-with': 'XMLHttpRequest',
    }

    auth_failed = False
    api_failed = False
    failure_detail = ''
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code in (401, 403):
            # 認證失敗：session 確定無效，直接拋 SessionExpired，不查日期
            auth_failed = True
            failure_detail = f'HTTP {response.status_code}'
        else:
            response.raise_for_status()
            body = response.json()
            if 'symbols' not in body or not body['symbols']:
                api_failed = True
                failure_detail = '回應缺少 symbols 欄位或為空（通常代表 session 過期被導向登入頁）'
            else:
                symbols = body['symbols']
    except TradingViewSessionExpired:
        raise
    except Exception as e:
        api_failed = True
        failure_detail = f'{type(e).__name__}: {e}'

    if auth_failed:
        # 401/403 = session 確定失效，無論 expires_at 為何
        raise _build_session_expired_error(expires_at)

    if api_failed:
        if _is_session_likely_expired(expires_at):
            raise _build_session_expired_error(expires_at)
        logger.warning('TradingView API 失敗但 session 尚未到期 (%s)，視為暫時性錯誤', failure_detail)
        raise RuntimeError(f'TradingView 暫時無法存取: {failure_detail}')

    return _parse_symbols(symbols)


def _parse_symbols(symbols: List[str]) -> Tuple[Dict, Dict]:
    """將 TradingView API 回傳的 symbols 解析為 watchlist + stock_info。"""
    watchlist: Dict = {}
    stock_info: Dict = {}
    current_key = None

    for item in symbols:
        if '###' in item:
            current_key = item.strip('###\u2064')
            watchlist[current_key] = {}
        elif current_key:
            if ':' not in item:
                continue
            provider, code = item.split(':', 1)
            if provider not in watchlist[current_key]:
                watchlist[current_key][provider] = []

            if provider in ('NASDAQ', 'NYSE', 'AMEX'):
                yf_code = code
                country = 'US'
            elif provider == 'TWSE':
                yf_code = f'{code}.TW'
                country = 'TW'
            elif provider == 'TPEX':
                yf_code = f'{code}.TWO'
                country = 'TW'
            else:
                continue

            watchlist[current_key][provider].append(yf_code)
            stock_info[yf_code] = {
                'country': country,
                'industry': current_key,
                'provider': provider,
                'original_code': code,
            }

    return watchlist, stock_info


# =============================================================================
# 使用者自定義 portfolio（無 TradingView 來源）
# =============================================================================
def build_stock_info_from_portfolio(symbols: List[str]) -> Dict:
    """
    當使用者直接傳入 portfolio 時，建立 stock_info。

    規則：
    - 含 '.TW' / '.TWO' → 台股
    - 其餘 → 美股
    - industry 統一標為 'Custom'，避開 NON_TRADABLE_INDUSTRIES 過濾
    """
    stock_info: Dict = {}
    for sym in symbols:
        if sym.endswith('.TW'):
            country, provider = 'TW', 'TWSE'
        elif sym.endswith('.TWO'):
            country, provider = 'TW', 'TPEX'
        else:
            country, provider = 'US', 'NASDAQ'
        stock_info[sym] = {
            'country': country,
            'industry': 'Custom',
            'provider': provider,
            'original_code': sym.split('.')[0],
        }
    return stock_info


# =============================================================================
# 股價歷史
# =============================================================================
def fetch_stock_history(ticker: str, period: str = DATA_PERIOD) -> pd.DataFrame:
    cache_key = f'stock__{ticker}__{period}'
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached
    try:
        df = yf.Ticker(ticker).history(period=period, interval='1d')
        if df.empty:
            return pd.DataFrame()
        df = df.tz_localize(None).sort_index()
        result = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        _save_cache(cache_key, result)
        return result
    except Exception as e:
        logger.debug('%s: %s', ticker, e)
        return pd.DataFrame()


def fetch_all_stock_data(stock_info: Dict) -> Dict:
    """根據 stock_info 抓取所有股票歷史資料。"""
    raw_data: Dict = {}
    total = len(stock_info)
    for i, ticker in enumerate(stock_info.keys()):
        df = fetch_stock_history(ticker)
        if df.empty or len(df) < MIN_HISTORY_DAYS:
            logger.debug('[%d/%d] %s: 資料不足，略過', i + 1, total, ticker)
            continue
        raw_data[ticker] = df
    logger.info('股價抓取完成: %d/%d', len(raw_data), total)
    return raw_data


# =============================================================================
# 日期對齊
# =============================================================================
def align_data_with_bfill(raw_data: Dict) -> Tuple[Dict, pd.DatetimeIndex]:
    """將多檔股票日期對齊到統一交易日索引（有效交易日 = 至少 N 檔有資料）。"""
    if not raw_data:
        return {}, pd.DatetimeIndex([])

    date_stock_count: Dict = {}
    for df in raw_data.values():
        if df.empty:
            continue
        for d in df.index:
            date_stock_count[d] = date_stock_count.get(d, 0) + 1

    min_required = min(MIN_STOCKS_FOR_VALID_DAY, max(1, int(len(raw_data) * MIN_STOCKS_FOR_VALID_DAY_RATIO)))
    valid_dates = [d for d, c in date_stock_count.items() if c >= min_required]
    if not valid_dates:
        valid_dates = list(date_stock_count.keys())

    unified_dates = pd.DatetimeIndex(sorted(valid_dates))
    aligned_data = {
        t: df.reindex(unified_dates).bfill().ffill()
        for t, df in raw_data.items() if not df.empty
    }
    return aligned_data, unified_dates


def build_close_df(aligned_data: Dict) -> pd.DataFrame:
    close_dict = {t: df['Close'] for t, df in aligned_data.items() if 'Close' in df.columns}
    if not close_dict:
        return pd.DataFrame()
    return pd.DataFrame(close_dict).sort_index()


def filter_by_market(close_df: pd.DataFrame, stock_info: Dict, market: str) -> Tuple[pd.DataFrame, Dict]:
    if market == 'global':
        return close_df, stock_info
    target_country = 'US' if market == 'us' else 'TW'
    keep = [t for t in close_df.columns if stock_info.get(t, {}).get('country') == target_country]
    filtered_info = {t: i for t, i in stock_info.items() if i.get('country') == target_country}
    return close_df[keep], filtered_info


# =============================================================================
# 基準指數（benchmark）價格
# =============================================================================
def fetch_benchmark_prices(symbol: str, period: str = '6y') -> Dict[str, float]:
    """抓取 benchmark 指數收盤價，回傳 {YYYY-MM-DD: close}。"""
    cache_key = f'benchmark__{symbol}__{period}'
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached
    try:
        df = yf.Ticker(symbol).history(period=period, interval='1d')
        if df.empty:
            return {}
        df = df.tz_localize(None).sort_index()
        result = {d.strftime('%Y-%m-%d'): float(r['Close']) for d, r in df.iterrows() if pd.notna(r['Close'])}
        _save_cache(cache_key, result)
        return result
    except Exception as e:
        logger.warning('Benchmark %s 抓取失敗: %s', symbol, e)
        return {}


# =============================================================================
# LINE 推播（共用，main.py 與 dashboard.py 均 import 此處）
# =============================================================================
def _load_line_credentials() -> tuple[str, str]:
    """從 config.yaml 讀取 LINE 憑證。未設定時回傳空字串。"""
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        line_cfg = cfg.get('line', {})
        return line_cfg.get('channel_access_token', ''), line_cfg.get('group_id', '')
    except Exception as e:
        logger.warning('無法讀取 LINE 憑證 (%s): %s', CONFIG_FILE, e)
        return '', ''


def push_line_message(text: str) -> dict:
    """推送 LINE 訊息。回傳 {'sent': bool, 'reason'?: str}。"""
    token, group_id = _load_line_credentials()
    if not (token and group_id):
        return {'sent': False, 'reason': 'LINE 憑證未設定（config.yaml）'}
    try:
        from linebot import LineBotApi
        from linebot.models import TextSendMessage
        LineBotApi(token).push_message(group_id, TextSendMessage(text=text))
        return {'sent': True}
    except Exception as e:
        logger.error('LINE 推播失敗: %s', e)
        return {'sent': False, 'reason': f'{type(e).__name__}: {e}'}


def push_session_expired_alert(expires_at: str | None) -> None:
    """TradingView session 已過期時推 LINE 警告（LINE 未設定則靜默略過）。"""
    msg = (
        '⚠️ Portfolio Optimizer 警告\n'
        f'TradingView session 已失效（expires_at: {expires_at}）\n'
        '請至 tradingview.com 重新登入，\n'
        '取得新的 sessionid cookie 後填入 config.yaml。'
    )
    result = push_line_message(msg)
    logger.info('session 過期警告 LINE %s', '已發送' if result['sent'] else f'未發送（{result.get("reason", "")}）')


def push_session_expiring_soon_alert(expires_at: str | None) -> None:
    """若 session 將於 7 天內到期，推送 LINE 預警。"""
    if not expires_at:
        return
    try:
        days_left = (datetime.strptime(expires_at, '%Y-%m-%d').date() - date.today()).days
        if days_left > 7:
            return
        if days_left <= 0:
            urgency = '《立刻》'
        elif days_left == 1:
            urgency = '《明天》'
        else:
            urgency = f'《{days_left} 天後》'
        msg = (
            f'⏰ Portfolio Optimizer 到期預警\n'
            f'TradingView session 將{urgency}失效\n'
            f'到期日：{expires_at}（剩 {max(days_left, 0)} 天）\n'
            '請提前至 tradingview.com 重新登入，\n'
            '取得新 sessionid 填入 config.yaml。'
        )
        result = push_line_message(msg)
        logger.info('session 到期預警 LINE %s（剩 %d 天）',
                    '已發送' if result['sent'] else f'未發送（{result.get("reason", "")}）', days_left)
    except Exception as e:
        logger.warning('到期預警推播失敗: %s', e)


def push_error_alert(code: str, message: str) -> None:
    """GCF 執行失敗時推 LINE 告警（LINE 未設定則靜默略過）。"""
    msg = (
        f'❌ Portfolio Optimizer 執行失敗\n'
        f'錯誤代碼：{code}\n'
        f'訊息：{message}\n'
        '請至 Cloud Logging 查看完整 traceback。'
    )
    result = push_line_message(msg)
    logger.info('錯誤告警 LINE %s（%s）',
                '已發送' if result['sent'] else '未發送', code)
