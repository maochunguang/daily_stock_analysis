# Phase 0 + Phase 1 实施记录

> 状态：已完成骨架与核心回测链路，测试通过。上游仓库已拉取到 `upstream/`（只读，不提交个人改动）。

## 1. 已实现

### Phase 0：脚手架与契约

- `personal/` 包、`pyproject.toml`、CLI 入口
- `personal/config.py`：环境变量 + `config/personal.env`
- `personal/contracts/`：
  - 只读打开上游 SQLite（`mode=ro` + `PRAGMA query_only`）
  - 上游表/字段契约检查
  - `analysis_history`、`portfolio_accounts`、`portfolio_trades`、`decision_signals` 的类型化读取
- `scripts/sync_upstream.sh`：同步上游并跑契约检查
- `scripts/check_contracts.py`：契约校验（支持 `--allow-missing`）
- `scripts/apply_patches.sh`：可选补丁检查/应用

### Phase 1：数据质量 + 组合回测

- `personal/datahub/`
  - SQLite 存储：`daily_bar`、`adjust_factor`、`trading_status`、`fund_nav`、`etf_snapshot`、`data_quality_event`、`backtest_*`、`trade_journal`
  - 复权：前复权/后复权（Tushare `adj_factor` 口径）
  - 交易性：T+1、100 股整数倍、停牌、涨跌停
  - 质量校验：OHLC 合法性、重复日期、极端跳空、非正价格、跨源价格/成交量偏差
  - 数据源适配：`synthetic`、`tushare`、`akshare`、`baostock`（后三者懒加载）
  - 同步服务：按优先级 fallback，自动写入质量事件
- `personal/backtest/`
  - 组合账本：FIFO lots、T+1 可用数量、已实现/未实现盈亏、费用
  - 成本模型：佣金（最低 5 元）、印花税（卖出 0.05%，ETF 免）、过户费、滑点、分红税
  - 执行模拟：次日开盘成交、涨跌停/停牌拦截、整手买入、现金约束
  - 绩效：累计/年化收益、波动、Sharpe、最大回撤、Calmar、基准/超额、胜率、盈亏比、换手、费用
  - 上游信号回放：`analysis_history.operation_advice` / `decision_signals.action` → buy/sell → 组合回测
- `personal/plugins/`
  - 稳定插件 API（只依赖 `personal.plugins.api`）
  - manifest 校验（`api_version`、类型、entry、requires、permissions）
  - 目录发现 + 隔离加载；单插件失败不影响其他插件
  - OBV 示例插件（`plugins/obv/`）
- `qmt-bridge/`
  - Windows FastAPI 桥接骨架：`/health`、`/quote`、`/positions`、`/orders`、`/cancels`、`/trades`、`/reconcile`
  - `mock` / `xtquant` 双模式；Token 鉴权；幂等键
  - `personal/execution/qmt_client.py`：macOS 侧 stdlib HTTP 客户端
- `personal/api/`
  - 本地 Web 控制台：总览、数据同步、回测、插件、上游、QMT 健康检查
  - 纯 HTML/CSS/JS，无前端构建步骤；内联 SVG 净值曲线

## 2. 测试

```bash
.venv/bin/python -m pytest -q
```

当前覆盖：54 个测试，包含：

- 代码/ETF 归一化
- 复权因子与除权跳空
- T+1/整手/涨跌停
- 成本模型（佣金最低值、印花税、ETF 免印花税、分红税、滑点）
- 组合账本（FIFO、T+1、现金约束、净值）
- 回测引擎（次日成交、涨停拦截、基准归一化）
- 指标（收益/回撤/基准超额/Wilson 区间）
- 数据源 fallback、质量事件、复权因子同步
- 上游契约读取、信号映射、端到端 replay
- 插件 manifest/加载/OBV 计算

## 3. 常用命令

```bash
# 初始化个人库
.venv/bin/python -m personal.cli.main init-db

# 查看配置与上游契约状态
.venv/bin/python -m personal.cli.main info

# 合成数据回测（无需外部数据源）
.venv/bin/python -m personal.cli.main demo --days 400

# 同步日线（先用合成数据验证链路）
PERSONAL_STOCK_LIST=600519,510050 \
  .venv/bin/python -m personal.cli.main sync --source synthetic \
  --start 2026-01-01 --end 2026-03-01

# 同步真实免费数据（需先安装可选依赖）
uv pip install --python .venv/bin/python -e ".[data]"
.venv/bin/python -m personal.cli.main sync --source akshare \
  --code 600519 --start 2025-01-01 --end 2026-11-12

# 复权因子（当前 Tushare 适配器支持）
.venv/bin/python -m personal.cli.main sync --dataset adjust --source tushare \
  --code 600519 --start 2025-01-01 --end 2026-11-12

# 回放上游 AI 建议（需 upstream/data/stock_analysis.db 已生成，且本地有日线）
.venv/bin/python -m personal.cli.main replay --start 2025-01-01 --end 2026-11-12 --save

# 插件列表
.venv/bin/python -m personal.cli.main plugins

# 本地 Web 控制台
.venv/bin/dsa-personal web --host 127.0.0.1 --port 8765
# 浏览器打开 http://127.0.0.1:8765/
```

## 4. 真实数据验证（2026-11-12）

### BaoStock（免费）

已成功同步：

```text
600519.SH: 34 bars from baostock
000001.SZ: 34 bars from baostock
510050.SH: 34 bars from baostock
```

- 0 个质量事件
- 真实日线 + 成本模型 + T+1/整手/涨跌停回测已跑通
- Tushare 与 BaoStock 同一区间交叉校验：**0 个价格/成交量偏差**

### Tushare 免费积分实测

| 接口 | 结果 |
|---|---|
| `daily` | ✅ 可调用 |
| `daily_basic` | ✅ 可调用 |
| `adj_factor` | ✅ 可调用，但免费档 **1 次/小时**，不适合批量回填 |
| `opt_basic` | ✅ 可调用 |
| `opt_daily` | ✅ 可调用 |
| `index_daily` | ✅ 可调用 |
| `fund_basic` / `fund_nav` / `fund_daily` / `fund_portfolio` | ❌ 无权限 |
| `index_weight` | ❌ 无权限 |

结论：

- 股票日线/每日指标/期权日线可以用免费 Tushare 测试。
- 复权因子免费档频率太低；批量复权建议升 **2000/5000 积分**，或先用 BaoStock 的复权行情。
- 基金数据先用 AkShare/天天基金；Tushare 基金接口需要 2000/5000 积分。
- Tushare 适配器已改为 **raw HTTP API**，不再依赖 `tushare` SDK 和 `lxml`。

## 5. 已知边界

- `sync --source auto` 会按 `tushare → baostock → akshare` 构建链路；某个源失败会自动 fallback。
- `get_bars` 现在按 `preferred_sources` 只选一个源，避免 synthetic/真实数据混读；默认优先 Tushare，其次 BaoStock。
- 复权因子目前只有 Tushare 适配器；免费档 1 次/小时，批量同步需要付费积分或 BaoStock 复权行情。
- 交易状态（停牌/ST/涨跌停）已支持存储与回测拦截，但尚未从数据源批量同步；下一步补 Tushare `suspend_d`/`stk_limit`/`limit_list_d` 适配器。
- 基金分析、交易日志 UI、复盘报告尚未实现（Phase 2）。
- QMT bridge 是骨架，尚未在真实中信建投 QMT 上联调；先跑 `QMT_MODE=mock`。
- 上游 DB 当前不存在（未运行上游），`info`/`replay` 会提示缺失；先运行一次上游分析即可。

## 6. 下一步

1. 补 Tushare/AkShare 的 `fetch_trading_status`，把停牌/ST/涨跌停落库。
2. 把复权因子应用到回测数据入口（当前引擎接收已处理 bars，需在 `DataPortal` 中统一调用 `adjust_bars`）。
3. Phase 2：基金净值/折溢价/跟踪误差、交易日志、日/周/月复盘报告。
4. Phase 3：QMT mock → 模拟盘 → 小资金实盘，补对账与断线重连。
5. Tushare 积分建议：先 2000（200 元/年）覆盖 daily_basic/基金净值；要基金持仓/期权日线批量回填再上 5000（500 元/年）。
