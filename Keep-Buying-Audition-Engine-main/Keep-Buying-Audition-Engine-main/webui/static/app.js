/**
 * Portfolio Optimizer — 前端主邏輯
 * 職責：
 *  1. 頁面載入時從 /api/config 讀取 config.yaml 填入表單
 *  2. 執行回測 → /api/backtest → 渲染權益曲線、績效指標、持倉、交易、產業排名
 *  3. 儲存憑證 / 儲存策略 → /api/config（POST）
 */

// ── 全域狀態 ─────────────────────────────────────────────────────────────────
let equityChart = null;

// ── DOM 就緒 ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  console.log('[app] DOMContentLoaded — 初始化開始');
  // 狀態字不寫死在 HTML：JS 第一行才登記，確保與後端 log 時序對齊
  setStatus('連線中…', 'running');
  try {
    initChart();
    console.log('[app] ECharts 初始化完成');
  } catch (e) {
    console.error('[app] ECharts 初始化失敗（CDN 未載入？）:', e);
  }
  loadConfig();
});

// ── 工具 ─────────────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }

function setStatus(msg, state = '') {
  $('status-text').textContent = msg;
  const dot = $('status-dot');
  dot.className = 'status-dot' + (state ? ' ' + state : '');
}


// ── Tab 切換 ──────────────────────────────────────────────────────────────────
function switchTab(id) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  // 對應按鈕：tab-base→0, tab-buy→1, tab-sell→2
  const idx = {'tab-base':0,'tab-buy':1,'tab-sell':2}[id] ?? 0;
  document.querySelectorAll('.tab-btn')[idx].classList.add('active');
}
function setSelectValue(id, value) {
  const el = $(id);
  if (el && value && [...el.options].some(o => o.value === String(value))) el.value = String(value);
}

// ── 條件欄位填入 ──────────────────────────────────────────────────────────────
function fillConditions(bt) {
  const bc = bt.buy_conditions  || {};
  const sc = bt.sell_conditions || {};
  const rs = bt.rebalance_strategy || {};

  // 買進
  setCheck('buy-sharpe-rank-enabled',       bc.sharpe_rank?.enabled);
  setNum  ('buy-sharpe-rank-top_n',         bc.sharpe_rank?.top_n);
  setCheck('buy-sharpe-threshold-enabled',  bc.sharpe_threshold?.enabled);
  setNum  ('buy-sharpe-threshold-threshold',bc.sharpe_threshold?.threshold);
  setCheck('buy-growth-streak-enabled',     bc.growth_streak?.enabled);
  setNum  ('buy-growth-streak-days',        bc.growth_streak?.days);
  setNum  ('buy-growth-streak-percentile',  bc.growth_streak?.percentile);
  setCheck('buy-sort-sharpe-enabled',       bc.sort_sharpe?.enabled);

  // 再平衡
  setSelectValue('rebalance-type',          rs.type);
  setNum  ('rebalance-top_n',               rs.top_n);
  setNum  ('rebalance-sharpe_threshold',    rs.sharpe_threshold);

  // 賣出
  setCheck('sell-sharpe-fail-enabled',      sc.sharpe_fail?.enabled);
  setNum  ('sell-sharpe-fail-periods',      sc.sharpe_fail?.periods);
  setNum  ('sell-sharpe-fail-top_n',        sc.sharpe_fail?.top_n);
  setCheck('sell-drawdown-enabled',         sc.drawdown?.enabled);
  setNum  ('sell-drawdown-threshold',       sc.drawdown?.threshold);
  setCheck('sell-growth-fail-enabled',      sc.growth_fail?.enabled);
  setNum  ('sell-growth-fail-days',         sc.growth_fail?.days);
  setCheck('sell-not-selected-enabled',     sc.not_selected?.enabled);
  setNum  ('sell-not-selected-periods',     sc.not_selected?.periods);
}

function setCheck(id, val) {
  const el = $(id);
  if (el && val !== undefined) el.checked = Boolean(val);
}
function setNum(id, val) {
  const el = $(id);
  if (el && val !== undefined && val !== null) el.value = val;
}

// ── 條件欄位收集 ──────────────────────────────────────────────────────────────
function collectConditions() {
  const chk = id => $(id)?.checked ?? false;
  const num = id => parseFloat($(id)?.value) || 0;
  const int = id => parseInt($(id)?.value, 10) || 0;
  return {
    buy_conditions: {
      sharpe_rank:      { enabled: chk('buy-sharpe-rank-enabled'),      top_n: int('buy-sharpe-rank-top_n') },
      sharpe_threshold: { enabled: chk('buy-sharpe-threshold-enabled'), threshold: num('buy-sharpe-threshold-threshold') },
      growth_streak:    { enabled: chk('buy-growth-streak-enabled'),    days: int('buy-growth-streak-days'), percentile: int('buy-growth-streak-percentile') },
      sort_sharpe:      { enabled: chk('buy-sort-sharpe-enabled') },
    },
    sell_conditions: {
      sharpe_fail:   { enabled: chk('sell-sharpe-fail-enabled'),    periods: int('sell-sharpe-fail-periods'), top_n: int('sell-sharpe-fail-top_n') },
      drawdown:      { enabled: chk('sell-drawdown-enabled'),        threshold: num('sell-drawdown-threshold') },
      growth_fail:   { enabled: chk('sell-growth-fail-enabled'),     days: int('sell-growth-fail-days'), threshold: 0 },
      not_selected:  { enabled: chk('sell-not-selected-enabled'),    periods: int('sell-not-selected-periods') },
    },
    rebalance_strategy: {
      type:              $('rebalance-type')?.value || 'delayed',
      top_n:             int('rebalance-top_n'),
      sharpe_threshold:  num('rebalance-sharpe_threshold'),
    },
  };
}


// ── 圖表初始化 ────────────────────────────────────────────────────────────────
function initChart() {
  equityChart = echarts.init($('equity-chart'));
  equityChart.setOption({
    backgroundColor: '#0d1117',
    animation: false,
    grid: { left: 70, right: 20, top: 16, bottom: 36 },
    xAxis: {
      type: 'category', data: [],
      axisLine:  { lineStyle: { color: '#30363d' } },
      axisLabel: { color: '#8b949e', fontSize: 10 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value', scale: true, position: 'right',
      axisLine:  { lineStyle: { color: '#30363d' } },
      axisLabel: { color: '#8b949e', fontSize: 10, formatter: v => v.toLocaleString() },
      splitLine: { lineStyle: { color: '#21262d' } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#161b22', borderColor: '#30363d',
      textStyle: { color: '#c9d1d9', fontSize: 11 },
    },
    legend: {
      top: 0, right: 20,
      textStyle: { color: '#8b949e', fontSize: 10 },
    },
    dataZoom: [{ type: 'inside', xAxisIndex: 0 }],
    series: [],
  });
}

// ── 讀取 config.yaml 填入表單 ─────────────────────────────────────────────────
async function loadConfig() {
  console.log('[loadConfig] 開始 → GET /api/config');
  setStatus('讀取配置中…');
  try {
    const resp = await fetch('/api/config');
    console.log('[loadConfig] 收到回應 status=%d', resp.status);
    const data = await resp.json();
    if (!data.ok) {
      console.error('[loadConfig] API 回傳 ok=false:', data.error);
      setStatus('無法載入 config.yaml', 'error');
      return;
    }
    const cfg = data.config || {};
    console.log('[loadConfig] config 解析成功，sections:', Object.keys(cfg));

    const tv = cfg.tradingview || {};
    $('tv-session-id').value   = tv.session_id   || '';
    $('tv-watchlist-id').value = tv.watchlist_id || '';
    $('tv-expires-at').value   = tv.expires_at   || '';

    const line = cfg.line || {};
    $('line-token').value = line.channel_access_token || '';
    $('line-group').value = line.group_id             || '';

    const bt = cfg.backtest || {};
    setSelectValue('market',         bt.market);
    setSelectValue('rebalance-freq', bt.rebalance_freq);
    if (bt.initial_capital)  $('initial-capital').value  = bt.initial_capital;
    if (bt.amount_per_stock) $('amount-per-stock').value = bt.amount_per_stock;
    if (bt.max_positions)    $('max-positions').value    = bt.max_positions;
    if (bt.start_date)       $('start-date').value       = bt.start_date;

    fillConditions(bt);
    console.log('[loadConfig] 表單填入完成（含條件欄位）');
    setStatus('配置已載入，可執行回測', 'ok');
  } catch (e) {
    console.error('[loadConfig] 例外:', e);
    setStatus('載入失敗：' + e.message, 'error');
  }
}

// ── 部署配置：把表單上所有內容一次寫回 config.yaml ──────────────────────────
async function deployConfig() {
  const btn = $('deploy-btn');
  btn.disabled = true;
  setStatus('部署配置中…', 'running');
  try {
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tradingview: {
          session_id:   $('tv-session-id').value.trim(),
          watchlist_id: $('tv-watchlist-id').value.trim(),
          expires_at:   $('tv-expires-at').value,
        },
        line: {
          channel_access_token: $('line-token').value.trim(),
          group_id:             $('line-group').value.trim(),
        },
        backtest: {
          market:           $('market').value,
          initial_capital:  parseFloat($('initial-capital').value),
          amount_per_stock: parseFloat($('amount-per-stock').value),
          max_positions:    parseInt($('max-positions').value, 10),
          start_date:       $('start-date').value,
          rebalance_freq:   $('rebalance-freq').value,
          ...collectConditions(),
        },
      }),
    });
    const data = await resp.json();
    setStatus(data.ok ? '配置已部署至 config.yaml' : '部署失敗：' + data.error?.message, data.ok ? 'ok' : 'error');
  } catch (e) {
    setStatus('部署失敗：' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

// ── 重新配置：捨棄表單變更，從 config.yaml 重新載入 ────────────────────────
async function reloadConfig() {
  const btn = $('reload-btn');
  btn.disabled = true;
  setStatus('重新載入配置…', 'running');
  try {
    await loadConfig();
    setStatus('已重新載入 config.yaml', 'ok');
  } catch (e) {
    setStatus('載入失敗：' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

// ── 執行回測 ──────────────────────────────────────────────────────────────────
async function runBacktest() {
  console.log('[runBacktest] 開始 → POST /api/backtest');
  const btn = $('run-btn');
  btn.disabled = true;
  btn.textContent = '回測中…';
  setStatus('正在抓取股價並執行回測（首次約 30–60 秒）…', 'running');

  try {
    const resp = await fetch('/api/backtest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        backtest: {
          market:           $('market').value,
          initial_capital:  parseFloat($('initial-capital').value),
          amount_per_stock: parseFloat($('amount-per-stock').value),
          max_positions:    parseInt($('max-positions').value, 10),
          start_date:       $('start-date').value,
          end_date:         $('end-date').value || null,
          rebalance_freq:   $('rebalance-freq').value,
          ...collectConditions(),
        },
        notify: { line: false },
      }),
    });
    const data = await resp.json();
    console.log('[runBacktest] 收到回應 ok=%s', data.ok);
    if (!data.ok) {
      const err = data.error || {};
      console.error('[runBacktest] 回測失敗:', err);
      let msg = `[${err.code}] ${err.message}`;
      if (err.remediation) msg += '  →  ' + err.remediation;
      setStatus(msg, 'error');
      return;
    }
    console.log('[runBacktest] 回測成功，開始渲染結果');
    renderAll(data);
    const m = data.meta;
    setStatus(
      `完成：${m.data_range[0]} → ${m.data_range[1]}　${m.symbols_count} 檔　${m.execution_time_ms} ms`,
      'ok',
    );
  } catch (e) {
    setStatus('呼叫失敗：' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '執行回測';
  }
}

// ── 渲染所有結果 ──────────────────────────────────────────────────────────────
function renderAll(data) {
  renderEquityChart(data.equity_curve, data.benchmark_curve, data.benchmark_name, data.meta);
  renderIndustry(data.holdings);
  renderMetrics(data.result);
  renderHoldings(data.holdings);
  renderTrades(data.trades);
}

// ── 權益曲線 ──────────────────────────────────────────────────────────────────
function renderEquityChart(equity, benchmark, benchmarkName, meta) {
  $('chart-meta').textContent =
    `${meta.data_range[0]} → ${meta.data_range[1]}  |  ${meta.symbols_count} 檔標的`;

  equityChart.setOption({
    xAxis: { data: equity.map(p => p.date) },
    series: [
      {
        name: '策略權益',
        type: 'line',
        data: equity.map(p => p.equity),
        lineStyle: { color: '#58a6ff', width: 2 },
        symbol: 'none',
        areaStyle: { color: 'rgba(88,166,255,0.06)' },
      },
      {
        name: `基準（${benchmarkName}）`,
        type: 'line',
        data: benchmark.map(p => p.equity),
        lineStyle: { color: '#8b949e', width: 1.5, type: 'dashed' },
        symbol: 'none',
      },
    ],
  });
}

// ── 產業排名（從 holdings 衍生）─────────────────────────────────────────────
function renderIndustry(holdings) {
  const map = {};
  for (const h of holdings) {
    const ind = h.industry || 'Unknown';
    if (!map[ind]) map[ind] = { count: 0, pnl_sum: 0 };
    map[ind].count++;
    map[ind].pnl_sum += h.pnl_pct;
  }
  const rows = Object.entries(map)
    .map(([name, d]) => ({ name, count: d.count, avg_pnl: d.pnl_sum / d.count }))
    .sort((a, b) => b.avg_pnl - a.avg_pnl);

  const container = $('industry-list');
  if (!rows.length) {
    container.innerHTML = '<p class="empty-state">無持倉資料</p>';
    return;
  }
  container.innerHTML = rows.map(r => {
    const pnl = (r.avg_pnl * 100).toFixed(1);
    const cls = r.avg_pnl >= 0 ? 'pos' : 'neg';
    const sign = r.avg_pnl >= 0 ? '+' : '';
    return `<div class="industry-row">
      <span class="industry-name">${r.name}</span>
      <span class="industry-count">${r.count}檔</span>
      <span class="industry-pnl ${cls}">${sign}${pnl}%</span>
    </div>`;
  }).join('');
}

// ── 績效指標 ──────────────────────────────────────────────────────────────────
function renderMetrics(r) {
  const items = [
    { label: '初始資金',  value: r.initial_capital },
    { label: '最終資產',  value: r.final_equity },
    { label: '總報酬率',  value: r.total_return,        signed: true },
    { label: '年化報酬',  value: r.annualized_return,   signed: true },
    { label: 'Sharpe',    value: r.sharpe_ratio },
    { label: '最大回撤',  value: r.max_drawdown,        negative: true },
    { label: '勝率',      value: r.win_rate },
    { label: '交易筆數',  value: r.total_trades },
  ];
  $('metrics-grid').innerHTML = items.map(it => {
    let cls = '';
    if (it.signed)    cls = String(it.value).startsWith('-') ? 'neg' : 'pos';
    if (it.negative)  cls = 'neg';
    return `<div class="metric-item">
      <div class="metric-label">${it.label}</div>
      <div class="metric-value ${cls}">${it.value}</div>
    </div>`;
  }).join('');
}

// ── 持倉清單 ──────────────────────────────────────────────────────────────────
function renderHoldings(holdings) {
  const tbody = $('holdings-table').querySelector('tbody');
  if (!holdings.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="placeholder-text">無持倉</td></tr>';
    return;
  }
  tbody.innerHTML = holdings.map(h => {
    const pnl = (h.pnl_pct * 100).toFixed(2);
    const color = h.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)';
    return `<tr>
      <td>${h.symbol}</td>
      <td style="color:var(--text-muted)">${h.industry || '—'}</td>
      <td>${h.shares}</td>
      <td>${h.avg_cost}</td>
      <td>${h.current_price}</td>
      <td>${Math.round(h.market_value_twd).toLocaleString()}</td>
      <td style="color:${color};font-weight:600">${pnl}%</td>
      <td style="color:var(--text-muted)">${h.buy_date}</td>
    </tr>`;
  }).join('');
}

// ── 近期交易 ──────────────────────────────────────────────────────────────────
function renderTrades(trades) {
  const tbody = $('trades-table').querySelector('tbody');
  const recent = trades.slice(-20).reverse();
  if (!recent.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="placeholder-text">無交易</td></tr>';
    return;
  }
  tbody.innerHTML = recent.map(t => {
    const color = t.type === 'buy' ? 'var(--green)' : 'var(--red)';
    return `<tr>
      <td style="color:var(--text-muted)">${t.date}</td>
      <td>${t.symbol}</td>
      <td style="color:${color};font-weight:700">${t.type === 'buy' ? '買入' : '賣出'}</td>
      <td>${t.shares ?? '—'}</td>
      <td>${t.price ?? '—'}</td>
    </tr>`;
  }).join('');
}
