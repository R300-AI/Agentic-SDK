"""
回測引擎：配置驗證、指標計算、回測流程、benchmark、報表格式化。

依賴：data.py（Money / FX / 對齊資料 / benchmark 抓取）
"""
from __future__ import annotations

import copy
import logging
import math
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from data import (
    CONFIG_FILE, FX, NON_TRADABLE_INDUSTRIES, RISK_FREE_RATE, SHARPE_WINDOW, Money,
    align_data_with_bfill, build_close_df, build_stock_info_from_portfolio,
    fetch_all_stock_data, fetch_benchmark_prices, fetch_watchlist,
    filter_by_market, twd, usd,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 配置：DEFAULT_CONFIG + load_config
# =============================================================================
CONDITION_OPTIONS = {
    'buy_conditions': {
        'sharpe_rank': {'params': {'top_n': {'default': 15}}},
        'sharpe_threshold': {'params': {'threshold': {'default': 1.0}}},
        'sharpe_streak': {'params': {'days': {'default': 3}, 'top_n': {'default': 10}}},
        'growth_rank': {'params': {'top_n': {'default': 7}}},
        'growth_streak': {'params': {'days': {'default': 2}, 'percentile': {'default': 30}}},
        'sort_sharpe': {'params': {}},
        'sort_industry': {'params': {'per_industry': {'default': 2}}},
    },
    'sell_conditions': {
        'sharpe_fail': {'params': {'periods': {'default': 2}, 'top_n': {'default': 15}}},
        'growth_fail': {'params': {'days': {'default': 5}, 'threshold': {'default': 0}}},
        'not_selected': {'params': {'periods': {'default': 3}}},
        'drawdown': {'params': {'threshold': {'default': 0.40}, 'from_highest': {'default': False}}},
        'weakness': {'params': {'rank_k': {'default': 20}, 'periods': {'default': 3}}},
    },
    'rebalance_strategies': {
        'immediate': {'params': {}},
        'batch': {'params': {'batch_ratio': {'default': 0.20}}},
        'delayed': {'params': {'top_n': {'default': 5}, 'sharpe_threshold': {'default': 0}}},
        'concentrated': {'params': {'concentrate_top_k': {'default': 3}, 'lead_margin': {'default': 0.30}}},
        'none': {'params': {}},
    },
}

DEFAULT_CONFIG = {
    'initial_capital': 1_000_000,
    'amount_per_stock': 100_000,
    'max_positions': 10,
    'market': 'us',
    'start_date': '2025-09-29',
    'end_date': None,
    'rebalance_freq': 'weekly',
    'fees': {
        'us': {'rate': 0.003, 'min_fee': 15},
        'tw': {'rate': 0.006, 'min_fee': 0},
    },
    'buy_conditions': {
        'sharpe_rank': {'enabled': True, 'top_n': 15},
        'sharpe_threshold': {'enabled': True, 'threshold': 1.0},
        'sharpe_streak': {'enabled': False, 'days': 3, 'top_n': 10},
        'growth_streak': {'enabled': True, 'days': 2, 'percentile': 30},
        'growth_rank': {'enabled': False, 'top_n': 7},
        'sort_sharpe': {'enabled': True},
        'sort_industry': {'enabled': False, 'per_industry': 2},
    },
    'sell_conditions': {
        'sharpe_fail': {'enabled': True, 'periods': 2, 'top_n': 15},
        'growth_fail': {'enabled': False, 'days': 5, 'threshold': 0},
        'not_selected': {'enabled': False, 'periods': 3},
        'drawdown': {'enabled': True, 'threshold': 0.40, 'from_highest': False},
        'weakness': {'enabled': False, 'rank_k': 20, 'periods': 3},
    },
    'rebalance_strategy': {
        'type': 'delayed',
        'top_n': 5,
        'sharpe_threshold': 0,
        'batch_ratio': 0.20,
        'concentrate_top_k': 3,
        'lead_margin': 0.30,
    },
}


class ConfigError(ValueError):
    """回測配置欄位不合法。"""


def _fill_condition_params(result: dict) -> None:
    for group in ('buy_conditions', 'sell_conditions'):
        for cond_name, cond_val in result.get(group, {}).items():
            option = CONDITION_OPTIONS[group].get(cond_name)
            if not option:
                continue
            for p_name, p_spec in option['params'].items():
                cond_val.setdefault(p_name, p_spec['default'])

    strategy = result.get('rebalance_strategy', {})
    stype = strategy.get('type')
    option = CONDITION_OPTIONS['rebalance_strategies'].get(stype) if stype else None
    if option:
        for p_name, p_spec in option['params'].items():
            strategy.setdefault(p_name, p_spec['default'])


def _apply_config_layer(result: dict, layer: dict) -> None:
    """In-place：將 layer 疊加至 result。用於 DEFAULT_CONFIG < config.yaml < user_params 的三層優先級。"""
    for key in ('initial_capital', 'amount_per_stock', 'max_positions',
                'market', 'start_date', 'end_date', 'rebalance_freq', 'fees'):
        if key in layer:
            result[key] = layer[key]
    for key in ('buy_conditions', 'sell_conditions', 'rebalance_strategy'):
        if key not in layer:
            continue
        for ck, cv in layer[key].items():
            current = result[key].get(ck)
            if isinstance(current, dict) and isinstance(cv, dict):
                result[key][ck] = {**current, **cv}
            else:
                result[key][ck] = cv


def load_config(user_params: Optional[dict] = None) -> dict:
    """優先級：DEFAULT_CONFIG < config.yaml backtest 區 < user_params（request 傳入）。"""
    user_params = user_params or {}
    result = copy.deepcopy(DEFAULT_CONFIG)

    # 讀 config.yaml 的 backtest 區疊加於 DEFAULT_CONFIG 之上
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            file_cfg = yaml.safe_load(f) or {}
        _apply_config_layer(result, file_cfg.get('backtest', {}))
    except Exception:
        pass  # 讀不到 config.yaml 就用 DEFAULT_CONFIG

    # user_params（request 傳入）最終覆蓋
    _apply_config_layer(result, user_params)

    _fill_condition_params(result)
    _validate_config(result)
    return result


def _validate_config(config: dict) -> None:
    v = config.get('initial_capital')
    if not isinstance(v, (int, float)) or v <= 0:
        raise ConfigError(f'initial_capital 必須是正數，收到 {v!r}')
    v = config.get('amount_per_stock')
    if not isinstance(v, (int, float)) or v <= 0:
        raise ConfigError(f'amount_per_stock 必須是正數，收到 {v!r}')
    v = config.get('max_positions')
    if not isinstance(v, int) or not (1 <= v <= 100):
        raise ConfigError(f'max_positions 必須是 1–100 整數，收到 {v!r}')
    if config.get('market') not in {'us', 'tw', 'global'}:
        raise ConfigError(f'market 必須是 us/tw/global，收到 {config.get("market")!r}')
    if config.get('rebalance_freq') not in {'daily', 'weekly', 'monthly'}:
        raise ConfigError(f'rebalance_freq 必須是 daily/weekly/monthly')
    try:
        pd.Timestamp(config['start_date'])
    except Exception:
        raise ConfigError(f'start_date 無法解析: {config.get("start_date")!r}')
    if config.get('end_date') is not None:
        try:
            pd.Timestamp(config['end_date'])
        except Exception:
            raise ConfigError(f'end_date 無法解析: {config.get("end_date")!r}')
    stype = config.get('rebalance_strategy', {}).get('type')
    if stype not in {'immediate', 'batch', 'delayed', 'concentrated', 'none'}:
        raise ConfigError(f'rebalance_strategy.type 不合法: {stype!r}')


# =============================================================================
# 指標：Sharpe / Ranking / Growth
# =============================================================================
def _calculate_sharpe_matrix(close_df: pd.DataFrame) -> pd.DataFrame:
    returns = close_df.pct_change()
    daily_rf = RISK_FREE_RATE / SHARPE_WINDOW
    excess = returns - daily_rf
    rolling_mean = excess.rolling(window=SHARPE_WINDOW).mean()
    rolling_std = excess.rolling(window=SHARPE_WINDOW).std().replace(0, np.nan)
    sharpe = (rolling_mean / rolling_std) * np.sqrt(SHARPE_WINDOW)
    sharpe = sharpe.replace([np.inf, -np.inf], np.nan).bfill().ffill()
    return sharpe


def _compute_daily_ranks_by_country(matrix: pd.DataFrame, stock_info: dict) -> Dict[str, Dict[str, List[str]]]:
    if matrix is None or matrix.empty:
        return {}
    ranks: Dict = {}
    for d in matrix.index:
        date_str = str(d)[:10]
        row = matrix.loc[d].dropna()
        us = [(t, v) for t, v in row.items() if stock_info.get(t, {}).get('country') == 'US']
        tw = [(t, v) for t, v in row.items() if stock_info.get(t, {}).get('country') == 'TW']
        ranks[date_str] = {
            'US': [t for t, _ in sorted(us, key=lambda x: x[1], reverse=True)],
            'TW': [t for t, _ in sorted(tw, key=lambda x: x[1], reverse=True)],
        }
    return ranks


class Indicators:
    def __init__(self, close_df: pd.DataFrame, stock_info: dict):
        self.close = close_df
        self.stock_info = stock_info
        self._sharpe = None
        self._rank = None
        self._growth = None
        self._sharpe_rank_by_country = None
        self._growth_rank_by_country = None

    @property
    def sharpe(self) -> pd.DataFrame:
        if self._sharpe is None:
            self._sharpe = _calculate_sharpe_matrix(self.close)
        return self._sharpe

    @property
    def rank(self) -> pd.DataFrame:
        if self._rank is None:
            self._rank = self.sharpe.rank(axis=1, ascending=False, method='min')
        return self._rank

    @property
    def growth(self) -> pd.DataFrame:
        if self._growth is None:
            self._growth = self.rank.shift(1) - self.rank
        return self._growth

    @property
    def sharpe_rank_by_country(self):
        if self._sharpe_rank_by_country is None:
            self._sharpe_rank_by_country = _compute_daily_ranks_by_country(self.sharpe, self.stock_info)
        return self._sharpe_rank_by_country

    @property
    def growth_rank_by_country(self):
        if self._growth_rank_by_country is None:
            self._growth_rank_by_country = _compute_daily_ranks_by_country(self.growth, self.stock_info)
        return self._growth_rank_by_country

    def get_dates(self) -> List[str]:
        return [str(d)[:10] for d in self.close.index]

    def get_sharpe(self, symbol: str, idx: int) -> float:
        return self.sharpe.iloc[idx].get(symbol, np.nan)

    def get_growth(self, symbol: str, idx: int) -> float:
        return self.growth.iloc[idx].get(symbol, np.nan)

    def check_in_sharpe_top_k(self, symbol: str, date_str: str, country: str, top_k: int) -> bool:
        return symbol in self.sharpe_rank_by_country.get(date_str, {}).get(country, [])[:top_k]

    def check_in_growth_top_k(self, symbol: str, date_str: str, country: str, top_k: int) -> bool:
        return symbol in self.growth_rank_by_country.get(date_str, {}).get(country, [])[:top_k]

    def get_sharpe_rank_position(self, symbol: str, date_str: str, country: str) -> int:
        ranking = self.sharpe_rank_by_country.get(date_str, {}).get(country, [])
        try:
            return ranking.index(symbol)
        except ValueError:
            return -1

    def get_growth_rank_position(self, symbol: str, date_str: str, country: str) -> int:
        ranking = self.growth_rank_by_country.get(date_str, {}).get(country, [])
        try:
            return ranking.index(symbol)
        except ValueError:
            return -1

    def check_in_growth_top_percentile(self, symbol: str, date_str: str, country: str, percentile: float) -> bool:
        ranking = self.growth_rank_by_country.get(date_str, {}).get(country, [])
        if not ranking:
            return False
        top_n = max(1, math.ceil(len(ranking) * percentile / 100))
        return symbol in ranking[:top_n]

    def check_sharpe_streak(self, symbol: str, idx: int, days: int, top_n: int) -> bool:
        if idx < days - 1:
            return False
        country = self.stock_info.get(symbol, {}).get('country', 'US')
        dates = self.get_dates()
        for i in range(days):
            j = idx - i
            if j < 0 or not self.check_in_sharpe_top_k(symbol, dates[j], country, top_n):
                return False
        return True

    def check_growth_streak(self, symbol: str, idx: int, days: int, percentile: float = 50) -> bool:
        if idx < days - 1:
            return False
        country = self.stock_info.get(symbol, {}).get('country', 'US')
        dates = self.get_dates()
        for i in range(days):
            j = idx - i
            if j < 0 or not self.check_in_growth_top_percentile(symbol, dates[j], country, percentile):
                return False
        return True


# =============================================================================
# Trade / Position / Result 資料類
# =============================================================================
class TradeType(Enum):
    BUY = 'buy'
    SELL = 'sell'


@dataclass
class Trade:
    date: str
    symbol: str
    type: TradeType
    shares: int
    price: Money
    amount: Money
    amount_twd: Money
    fee: Money
    reason: str = ''
    profit: Money = field(default_factory=lambda: twd(0))

    def to_dict(self) -> dict:
        return {
            'date': self.date,
            'symbol': self.symbol,
            'type': self.type.value,
            'shares': self.shares,
            'price': str(self.price),
            'amount': str(self.amount),
            'amount_twd': f'${self.amount_twd.amount:,.0f}',
            'fee': f'${self.fee.amount:,.0f}',
            'reason': self.reason,
            'profit': f'${self.profit.amount:+,.0f}' if self.profit.amount != 0 else '',
        }


@dataclass
class Position:
    symbol: str
    shares: int
    avg_cost: Money
    cost_basis: Money
    buy_date: str
    buy_price: Money
    peak_price: float = 0.0
    country: str = 'US'


@dataclass
class BacktestResult:
    initial_capital: Money
    final_equity: Money
    total_return: float
    annualized_return: float
    total_trades: int
    win_trades: int
    loss_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    trades: list
    equity_curve: list

    def to_dict(self) -> dict:
        return {
            'initial_capital': str(self.initial_capital),
            'final_equity': str(self.final_equity),
            'total_return': f'{self.total_return:.2%}',
            'annualized_return': f'{self.annualized_return:.2%}',
            'total_trades': self.total_trades,
            'win_trades': self.win_trades,
            'loss_trades': self.loss_trades,
            'win_rate': f'{self.win_rate:.2%}',
            'max_drawdown': f'{self.max_drawdown:.2%}',
            'sharpe_ratio': round(self.sharpe_ratio, 2),
        }


# =============================================================================
# 回測引擎（核心邏輯保留原樣）
# =============================================================================
class BacktestEngine:
    def __init__(self, close_df, indicators, stock_info, config, fx=None):
        self.close = close_df
        self.indicators = indicators
        self.stock_info = stock_info
        self.config = config
        self.fx = fx or FX()

        initial = config['initial_capital']
        self.cash: Money = initial if isinstance(initial, Money) else twd(initial)
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[dict] = []

        self._sharpe_fail_counter: Dict[str, int] = {}
        self._not_selected_counter: Dict[str, int] = {}
        self._weakness_counter: Dict[str, int] = {}

    def run(self, start_date, end_date) -> BacktestResult:
        date_index = self.close.index
        start_idx = date_index.searchsorted(start_date)
        end_idx = date_index.searchsorted(end_date, side='right') - 1
        logger.info('回測: %s ~ %s', date_index[start_idx].date(), date_index[end_idx].date())
        for idx in range(start_idx, end_idx + 1):
            self._process_day(idx)
        return self._calculate_result(start_idx, end_idx)

    def _process_day(self, idx: int):
        date_str = self.close.index[idx].strftime('%Y-%m-%d')
        self._update_peaks(idx)
        self._process_sells(idx, date_str)
        self._process_rebalance(idx, date_str)
        equity, holdings_value, holdings_snapshot = self._calc_equity_with_holdings(idx)
        self.equity_curve.append({
            'date': date_str,
            'equity': equity.amount,
            'cash': self.cash.amount,
            'holdingsValue': holdings_value,
            'holdings': holdings_snapshot,
        })

    def _update_peaks(self, idx: int):
        for sym, pos in self.positions.items():
            price = self.close.iloc[idx].get(sym, pos.peak_price)
            if price > pos.peak_price:
                pos.peak_price = price

    def _select_stocks(self, idx: int) -> List[str]:
        buy_cond = self.config['buy_conditions']
        candidates = []
        for symbol in self.close.columns:
            industry = self.stock_info.get(symbol, {}).get('industry', '')
            if industry in NON_TRADABLE_INDUSTRIES:
                continue
            if not self._check_buy(symbol, idx, buy_cond):
                continue
            candidates.append({
                'symbol': symbol,
                'sharpe': self.indicators.get_sharpe(symbol, idx),
                'industry': self.stock_info.get(symbol, {}).get('industry', 'Unknown'),
            })

        if buy_cond.get('sort_industry', {}).get('enabled'):
            per_industry = buy_cond['sort_industry']['per_industry']
            groups: Dict[str, list] = {}
            for c in candidates:
                groups.setdefault(c['industry'], []).append(c)
            for ind in groups:
                groups[ind].sort(key=lambda x: x['sharpe'] if x['sharpe'] is not None else -999, reverse=True)
            industries = sorted(
                groups.keys(),
                key=lambda i: (groups[i][0]['sharpe'] if groups[i][0]['sharpe'] is not None else -999),
                reverse=True,
            )
            selected, counts, has_more = [], {}, True
            max_rounds = per_industry * len(industries) + 1
            r = 0
            while has_more and r < max_rounds:
                has_more = False
                for ind in industries:
                    c = counts.get(ind, 0)
                    if c >= per_industry or c >= len(groups[ind]):
                        continue
                    selected.append(groups[ind][c])
                    counts[ind] = c + 1
                    has_more = True
                r += 1
            candidates = selected
        elif buy_cond.get('sort_sharpe', {}).get('enabled'):
            candidates.sort(key=lambda x: x['sharpe'] if x['sharpe'] is not None else -999, reverse=True)

        return [c['symbol'] for c in candidates]

    def _check_buy(self, symbol: str, idx: int, buy_cond: dict) -> bool:
        date_str = self.close.index[idx].strftime('%Y-%m-%d')
        country = self.stock_info.get(symbol, {}).get('country', 'US')
        if buy_cond.get('sharpe_rank', {}).get('enabled'):
            if not self.indicators.check_in_sharpe_top_k(symbol, date_str, country, buy_cond['sharpe_rank']['top_n']):
                return False
        if buy_cond.get('sharpe_threshold', {}).get('enabled'):
            sharpe = self.indicators.get_sharpe(symbol, idx)
            if pd.isna(sharpe) or sharpe < buy_cond['sharpe_threshold']['threshold']:
                return False
        if buy_cond.get('sharpe_streak', {}).get('enabled'):
            if not self.indicators.check_sharpe_streak(
                symbol, idx, buy_cond['sharpe_streak']['days'], buy_cond['sharpe_streak']['top_n']):
                return False
        if buy_cond.get('growth_streak', {}).get('enabled'):
            if not self.indicators.check_growth_streak(
                symbol, idx, buy_cond['growth_streak']['days'], buy_cond['growth_streak']['percentile']):
                return False
        if buy_cond.get('growth_rank', {}).get('enabled'):
            if not self.indicators.check_in_growth_top_k(symbol, date_str, country, buy_cond['growth_rank']['top_n']):
                return False
        return True

    def _process_sells(self, idx: int, date_str: str):
        sell_cond = self.config['sell_conditions']
        selected = set(self._select_stocks(idx))
        to_sell = []
        for symbol, pos in list(self.positions.items()):
            reason = self._check_sell(symbol, idx, sell_cond, selected, pos)
            if reason:
                to_sell.append((symbol, reason))
        for symbol, reason in to_sell:
            self._sell(symbol, idx, date_str, reason)

    def _check_sell(self, symbol, idx, sell_cond, selected, pos) -> Optional[str]:
        date_str = self.close.index[idx].strftime('%Y-%m-%d')
        country = self.stock_info.get(symbol, {}).get('country', 'US')

        if sell_cond.get('sharpe_fail', {}).get('enabled'):
            periods = sell_cond['sharpe_fail']['periods']
            top_n = sell_cond['sharpe_fail']['top_n']
            in_top = self.indicators.check_in_sharpe_top_k(symbol, date_str, country, top_n)
            self._sharpe_fail_counter[symbol] = 0 if in_top else self._sharpe_fail_counter.get(symbol, 0) + 1
            if self._sharpe_fail_counter.get(symbol, 0) >= periods:
                return f'sharpe_fail({periods})'

        if sell_cond.get('growth_fail', {}).get('enabled'):
            days = sell_cond['growth_fail']['days']
            threshold = sell_cond['growth_fail']['threshold']
            vals = []
            for i in range(days):
                j = idx - i
                if j >= 0:
                    g = self.indicators.get_growth(symbol, j)
                    if not pd.isna(g):
                        vals.append(g)
            if vals and (sum(vals) / len(vals)) < threshold:
                return f'growth_fail({days}d)'

        if sell_cond.get('not_selected', {}).get('enabled'):
            periods = sell_cond['not_selected']['periods']
            self._not_selected_counter[symbol] = 0 if symbol in selected else self._not_selected_counter.get(symbol, 0) + 1
            if self._not_selected_counter.get(symbol, 0) >= periods:
                return f'not_selected({periods})'

        if sell_cond.get('drawdown', {}).get('enabled'):
            threshold = sell_cond['drawdown']['threshold']
            from_highest = sell_cond['drawdown']['from_highest']
            price = self.close.iloc[idx].get(symbol, pos.buy_price.amount)
            ref = (pos.peak_price or pos.buy_price.amount) if from_highest else pos.buy_price.amount
            if ref > 0 and (ref - price) / ref >= threshold:
                return f'drawdown({threshold:.0%})'

        if sell_cond.get('weakness', {}).get('enabled'):
            rank_k = sell_cond['weakness']['rank_k']
            periods = sell_cond['weakness']['periods']
            sp = self.indicators.get_sharpe_rank_position(symbol, date_str, country)
            gp = self.indicators.get_growth_rank_position(symbol, date_str, country)
            bad = (sp < 0 or sp >= rank_k) and (gp < 0 or gp >= rank_k)
            self._weakness_counter[symbol] = self._weakness_counter.get(symbol, 0) + 1 if bad else 0
            if self._weakness_counter.get(symbol, 0) >= periods:
                return f'weakness({periods})'

        return None

    def _process_rebalance(self, idx: int, date_str: str):
        strategy = self.config['rebalance_strategy']
        stype = strategy['type']
        candidates = self._select_stocks(idx)
        to_buy = [s for s in candidates if s not in self.positions]
        # 每月 1 號摘要 + 首日摘要：診斷「為什麼不買」
        ts = self.close.index[idx]
        is_summary_day = ts.day <= 3 and (idx == 0 or self.close.index[idx - 1].month != ts.month)
        if is_summary_day:
            logger.info('[%s] 候選=%d 已持倉=%d 待買=%d 策略=%s',
                        date_str, len(candidates), len(self.positions), len(to_buy), stype)
        if not to_buy:
            return
        slots = self.config['max_positions'] - len(self.positions)
        if slots <= 0:
            return
        to_buy = to_buy[:slots]

        if stype == 'batch':
            invest = self.cash * strategy['batch_ratio']
            amount = invest / len(to_buy) if to_buy else twd(0)
            self._buy_stocks(to_buy, idx, date_str, amount)
        elif stype == 'immediate':
            self._buy_stocks(to_buy, idx, date_str, self._get_amount_per_stock())
        elif stype == 'concentrated':
            top_k = strategy['concentrate_top_k']
            lead_margin = strategy['lead_margin']
            market = self.config['market']
            top_k_t, next_k_t = [], []
            if market in ('global', 'us'):
                r = self.indicators.sharpe_rank_by_country.get(date_str, {}).get('US', [])
                top_k_t += r[:top_k]; next_k_t += r[top_k:top_k * 2]
            if market in ('global', 'tw'):
                r = self.indicators.sharpe_rank_by_country.get(date_str, {}).get('TW', [])
                top_k_t += r[:top_k]; next_k_t += r[top_k:top_k * 2]
            def avg(tickers):
                vs = [self.indicators.get_sharpe(t, idx) for t in tickers]
                vs = [v for v in vs if not pd.isna(v)]
                return sum(vs) / len(vs) if vs else 0
            top_avg, next_avg = avg(top_k_t), avg(next_k_t)
            should = (next_avg <= 0 and top_avg > 0) or (
                next_avg > 0 and (top_avg - next_avg) / abs(next_avg) >= lead_margin
            )
            if not should:
                return
            self._buy_stocks(to_buy[:top_k], idx, date_str, self._get_amount_per_stock())
        elif stype == 'delayed':
            top_n = strategy['top_n']
            sharpe_threshold = strategy['sharpe_threshold']
            market = self.config['market']
            vals = []
            if market in ('global', 'us'):
                for s in self.indicators.sharpe_rank_by_country.get(date_str, {}).get('US', [])[:top_n]:
                    sh = self.indicators.get_sharpe(s, idx)
                    if not pd.isna(sh):
                        vals.append(sh)
            if market in ('global', 'tw'):
                for s in self.indicators.sharpe_rank_by_country.get(date_str, {}).get('TW', [])[:top_n]:
                    sh = self.indicators.get_sharpe(s, idx)
                    if not pd.isna(sh):
                        vals.append(sh)
            avg_sh = sum(vals) / len(vals) if vals else 0
            if is_summary_day:
                logger.info('[%s] delayed gate: avg_sharpe=%.3f threshold=%.3f → %s',
                            date_str, avg_sh, sharpe_threshold,
                            'PASS（買進）' if avg_sh > sharpe_threshold else 'BLOCK（不買）')
            if avg_sh <= sharpe_threshold:
                return
            self._buy_stocks(to_buy, idx, date_str, self._get_amount_per_stock())

    def _get_amount_per_stock(self) -> Money:
        amt = self.config['amount_per_stock']
        return amt if isinstance(amt, Money) else twd(amt)

    def _buy_stocks(self, symbols, idx, date_str, amount_per_stock: Money):
        if not isinstance(amount_per_stock, Money):
            amount_per_stock = twd(amount_per_stock)
        half = amount_per_stock * 0.5
        for symbol in symbols:
            if self.cash < half:
                break
            if symbol in self.positions:
                continue
            price_raw = self.close.iloc[idx].get(symbol)
            if pd.isna(price_raw) or price_raw <= 0:
                continue
            country = self.stock_info.get(symbol, {}).get('country', 'US')
            is_us = country != 'TW'

            if is_us:
                price_money = usd(price_raw)
                budget_usd = self.fx.to_usd(amount_per_stock, date_str)
                shares = int(budget_usd.amount / price_raw)
            else:
                price_money = twd(price_raw)
                shares = int(amount_per_stock.amount / price_raw)
            if shares <= 0:
                continue

            if is_us:
                amount_original = usd(shares * price_raw)
                amount_twd = self.fx.to_twd(amount_original, date_str)
            else:
                amount_original = twd(shares * price_raw)
                amount_twd = amount_original

            fee_cfg = self.config['fees']['us' if is_us else 'tw']
            fee = twd(max(amount_twd.amount * fee_cfg['rate'], fee_cfg['min_fee']))
            total_cost = amount_twd + fee
            if total_cost > self.cash:
                continue

            self.cash = self.cash - total_cost
            self.positions[symbol] = Position(
                symbol=symbol, shares=shares, avg_cost=price_money,
                cost_basis=total_cost, buy_date=date_str, buy_price=price_money,
                peak_price=price_raw, country=country,
            )
            self.trades.append(Trade(
                date=date_str, symbol=symbol, type=TradeType.BUY,
                shares=shares, price=price_money, amount=amount_original,
                amount_twd=amount_twd, fee=fee, reason='buy',
            ))
            if len([t for t in self.trades if t.type == TradeType.BUY]) == 1:
                logger.info('[%s] 首筆買進：%s shares=%d cost_twd=%.0f', date_str, symbol, shares, total_cost.amount)

    def _sell(self, symbol, idx, date_str, reason):
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        price_raw = self.close.iloc[idx].get(symbol, pos.avg_cost.amount)
        is_us = pos.country != 'TW'
        if is_us:
            price_money = usd(price_raw)
            amount_original = usd(pos.shares * price_raw)
            amount_twd = self.fx.to_twd(amount_original, date_str)
        else:
            price_money = twd(price_raw)
            amount_original = twd(pos.shares * price_raw)
            amount_twd = amount_original
        fee_cfg = self.config['fees']['us' if is_us else 'tw']
        fee = twd(max(amount_twd.amount * fee_cfg['rate'], fee_cfg['min_fee']))
        profit = amount_twd - pos.cost_basis - fee
        self.cash = self.cash + amount_twd - fee
        del self.positions[symbol]
        for c in (self._sharpe_fail_counter, self._not_selected_counter, self._weakness_counter):
            c.pop(symbol, None)
        self.trades.append(Trade(
            date=date_str, symbol=symbol, type=TradeType.SELL,
            shares=pos.shares, price=price_money, amount=amount_original,
            amount_twd=amount_twd, fee=fee, reason=reason, profit=profit,
        ))

    def _calc_equity_with_holdings(self, idx: int):
        date_str = self.close.index[idx].strftime('%Y-%m-%d')
        equity = self.cash
        holdings_value = 0.0
        snapshot: Dict = {}
        for sym, pos in self.positions.items():
            price_raw = self.close.iloc[idx].get(sym, pos.avg_cost.amount)
            if pos.country != 'TW':
                mv = self.fx.to_twd(usd(pos.shares * price_raw), date_str)
            else:
                mv = twd(pos.shares * price_raw)
            equity = equity + mv
            holdings_value += mv.amount
            cb = pos.cost_basis.amount
            pnl_pct = (mv.amount - cb) / cb if cb > 0 else 0
            info = self.stock_info.get(sym, {})
            snapshot[sym] = {
                'shares': pos.shares,
                'avgCost': round(pos.avg_cost.amount, 2),
                'currentPrice': round(price_raw, 2),
                'marketValue': round(mv.amount, 0),
                'pnlPct': round(pnl_pct * 100, 2),
                'buyDate': pos.buy_date,
                'industry': info.get('industry', 'Unknown'),
                'country': pos.country,
            }
        return equity, holdings_value, snapshot

    def _calc_equity(self, idx: int) -> Money:
        equity, _, _ = self._calc_equity_with_holdings(idx)
        return equity

    def _calculate_result(self, start_idx: int, end_idx: int) -> BacktestResult:
        initial_cfg = self.config['initial_capital']
        initial = initial_cfg if isinstance(initial_cfg, Money) else twd(initial_cfg)
        final = self._calc_equity(end_idx)
        total_return = (final.amount - initial.amount) / initial.amount
        days = end_idx - start_idx + 1
        years = days / 252
        annualized = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        sells = [t for t in self.trades if t.type == TradeType.SELL]
        wins = sum(1 for t in sells if t.profit.amount > 0)
        losses = sum(1 for t in sells if t.profit.amount <= 0)
        win_rate = wins / len(sells) if sells else 0

        max_eq = initial.amount
        max_dd = 0
        for p in self.equity_curve:
            eq = p['equity']
            if eq > max_eq:
                max_eq = eq
            dd = (max_eq - eq) / max_eq if max_eq > 0 else 0
            if dd > max_dd:
                max_dd = dd

        if len(self.equity_curve) > 1:
            eqs = [p['equity'] for p in self.equity_curve]
            rets = np.diff(eqs) / np.array(eqs[:-1])
            sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252)) if np.std(rets) > 0 else 0
        else:
            sharpe = 0

        return BacktestResult(
            initial_capital=initial, final_equity=final,
            total_return=total_return, annualized_return=annualized,
            total_trades=len(self.trades), win_trades=wins, loss_trades=losses,
            win_rate=win_rate, max_drawdown=max_dd, sharpe_ratio=sharpe,
            trades=[t.to_dict() for t in self.trades],
            equity_curve=self.equity_curve,
        )


# =============================================================================
# Benchmark 曲線（直接從 yfinance 抓 ^IXIC / ^TWII / TWD=X）
# =============================================================================
def calculate_benchmark_curve(market: str, trading_dates: list, initial_capital: float, fx: FX) -> Tuple[list, str]:
    if not trading_dates:
        return [], ''

    if market == 'global':
        name = '國際加權指數'
        nasdaq = fetch_benchmark_prices('^IXIC')
        twii = fetch_benchmark_prices('^TWII')
        if not nasdaq or not twii:
            return [], name
        curve, first_n, first_t, first_fx = [], None, None, None
        for d in trading_dates:
            n, t = nasdaq.get(d), twii.get(d)
            if not (n and t):
                continue
            cfx = fx.rate(d)
            if first_n is None:
                first_n, first_t, first_fx = n, t, cfx
            us_eq = 0.5 * initial_capital * (n / first_n) * (cfx / first_fx)
            tw_eq = 0.5 * initial_capital * (t / first_t)
            curve.append({'date': d, 'equity': round(us_eq + tw_eq, 2)})
        return curve, name

    if market == 'tw':
        name = '台灣加權指數'
        prices = fetch_benchmark_prices('^TWII')
        if not prices:
            return [], name
        curve, first = [], None
        for d in trading_dates:
            p = prices.get(d)
            if not p:
                continue
            if first is None:
                first = p
            curve.append({'date': d, 'equity': round(initial_capital * (p / first), 2)})
        return curve, name

    name = 'NASDAQ'
    prices = fetch_benchmark_prices('^IXIC')
    if not prices:
        return [], name
    curve, first, first_fx = [], None, None
    for d in trading_dates:
        p = prices.get(d)
        if not p:
            continue
        cfx = fx.rate(d)
        if first is None:
            first, first_fx = p, cfx
        curve.append({'date': d, 'equity': round(initial_capital * (p / first) * (cfx / first_fx), 2)})
    return curve, name


# =============================================================================
# 當前持倉 snapshot 建構器（給回應 holdings 欄位用）
# =============================================================================
def build_current_holdings(engine: BacktestEngine, close_df: pd.DataFrame, end_dt) -> list:
    date_index = close_df.index
    actual_end_idx = date_index.searchsorted(end_dt, side='right') - 1
    end_date_str = close_df.index[actual_end_idx].strftime('%Y-%m-%d')
    fx = engine.fx

    holdings = []
    for symbol, pos in engine.positions.items():
        country = engine.stock_info.get(symbol, {}).get('country', 'US')
        current_price = close_df.iloc[actual_end_idx].get(symbol, pos.avg_cost.amount)
        if country == 'TW':
            price_money = twd(current_price)
            market_value = twd(pos.shares * current_price)
        else:
            price_money = usd(current_price)
            market_value = fx.to_twd(usd(pos.shares * current_price), end_date_str)
        cost_in_twd = pos.cost_basis
        pnl_pct = (market_value.amount - cost_in_twd.amount) / cost_in_twd.amount if cost_in_twd.amount > 0 else 0
        holdings.append({
            'symbol': symbol,
            'shares': pos.shares,
            'avg_cost': str(pos.avg_cost),
            'current_price': str(price_money),
            'market_value_twd': round(market_value.amount, 0),
            'pnl_pct': pnl_pct,
            'buy_date': pos.buy_date,
            'industry': engine.stock_info.get(symbol, {}).get('industry', 'Unknown'),
            'country': country,
        })
    holdings.sort(key=lambda x: x['buy_date'], reverse=True)
    return holdings


# =============================================================================
# Pipeline　—　唯一 Domain 入口，所有 Adapter（GCF main / CLI / WebUI）共用
# =============================================================================
def resolve_portfolio() -> Tuple[Dict, str]:
    """從 TradingView watchlist 取得投資組合。"""
    _, stock_info = fetch_watchlist()
    return stock_info, 'tradingview'


def run_pipeline(
    backtest_params: Optional[dict] = None,
) -> Dict:
    """完整回測管線：設定 → 資料 → 對齊 → 運行 → 基準 → 持仓 snapshot。

    Args:
        backtest_params: 使用者覆寫的回測參數，None 表示全用預設

    Returns:
        dict：config, result, current_holdings, benchmark_curve, benchmark_name,
              start_dt, end_dt, portfolio_source, symbols_count

    Raises:
        ConfigError: 參數不合法或日期超出資料範圍
        TradingViewSessionExpired: TradingView session 已過期
        RuntimeError: 資料抽取失敗或無可用標的
    """
    config = load_config(backtest_params or {})
    logger.info('config 載入完成： market=%s start=%s end=%s capital=%s max_positions=%s rebalance_freq=%s',
                config.get('market'), config.get('start_date'), config.get('end_date'),
                config.get('initial_capital'), config.get('max_positions'), config.get('rebalance_freq'))

    stock_info, portfolio_source = resolve_portfolio()
    logger.info('標的解析完成： source=%s count=%d', portfolio_source, len(stock_info))
    if not stock_info:
        raise RuntimeError('無可用標的（指定來源無資料）')

    raw_data = fetch_all_stock_data(stock_info)
    logger.info('資料抽取完成：成功=%d / 請求=%d', len(raw_data), len(stock_info))
    if not raw_data:
        raise RuntimeError('所有標的的歷史資料皆抽取失敗')

    aligned, _ = align_data_with_bfill(raw_data)
    close_df = build_close_df(aligned)
    logger.info('對齊完成：shape=%s date_range=%s〜%s',
                close_df.shape,
                close_df.index[0].date() if not close_df.empty else None,
                close_df.index[-1].date() if not close_df.empty else None)
    if close_df.empty:
        raise RuntimeError('對齊後無可用股價資料')

    market = config['market']
    close_df, stock_info = filter_by_market(close_df, stock_info, market)
    logger.info('市場過濾後：market=%s 剩餘標的=%d', market, len(stock_info))
    if close_df.empty:
        raise RuntimeError(f'{market} 市場無可用資料')

    end_date_str = config.get('end_date')
    end_dt_raw = pd.Timestamp(datetime.today().date()) if not end_date_str else pd.Timestamp(end_date_str)
    date_index = close_df.index
    end_idx = date_index.searchsorted(end_dt_raw, side='right') - 1
    if end_idx < 0:
        raise ConfigError(f'結束日期 {end_dt_raw.date()} 早於所有可用資料')
    end_dt = date_index[end_idx]

    start_idx = date_index.searchsorted(pd.Timestamp(config['start_date']), side='left')
    if start_idx >= len(date_index):
        raise ConfigError(f'開始日期 {config["start_date"]} 晚於所有可用資料')
    start_dt = date_index[start_idx]
    if start_dt >= end_dt:
        raise ConfigError(f'start_date {start_dt.date()} 必須早於 end_date {end_dt.date()}')
    logger.info('回測區間裁切：start=%s end=%s (共 %d 個交易日)',
                start_dt.date(), end_dt.date(), end_idx - start_idx + 1)

    indicators = Indicators(close_df, stock_info)
    fx = FX()
    engine = BacktestEngine(close_df, indicators, stock_info, config, fx)
    logger.info('開始執行回測引擎…')
    result = engine.run(start_date=start_dt, end_date=end_dt)
    logger.info('回測完成：equity_points=%d trades=%d',
                len(result.equity_curve), len(result.trades))

    benchmark_curve, benchmark_name = calculate_benchmark_curve(
        market, [p['date'] for p in result.equity_curve], config['initial_capital'], fx,
    )
    logger.info('基準指數計算完成：%s (%d 點)', benchmark_name, len(benchmark_curve))

    current_holdings = build_current_holdings(engine, close_df, end_dt)
    logger.info('當前持倉快照：%d 檔', len(current_holdings))

    return {
        'config': config,
        'result': result,
        'current_holdings': current_holdings,
        'benchmark_curve': benchmark_curve,
        'benchmark_name': benchmark_name,
        'start_dt': start_dt,
        'end_dt': end_dt,
        'portfolio_source': portfolio_source,
        'symbols_count': len(stock_info),
    }
