# 个人专业投资者扩展架构与技术方案

> 目标：在 **不修改上游主仓库核心代码** 的前提下，构建一套可持续跟随上游更新、低耦合、可插拔的个人扩展层。
>
> 范围：A 股股票 + 基金（当前）、ETF 期权（后续）；个人使用，不做机构级多租户/合规/OMS。
>
> 状态：**已实施**（Phase 0/1 + Web UI 集成）。
>
> **Fork 布局说明**：本文档最初按“外层工作区 + `upstream/` 只读克隆”描述。当前 fork 是自包含仓库：仓库根目录就是 DSA 上游代码，个人层位于 `personal/`，UI 补丁已应用。文中出现 `upstream/...` 时，在 fork 中按仓库根目录理解。

---

## 0. 一页纸结论

| 问题 | 决策 |
|---|---|
| 是否 fork 上游？ | **不 fork 核心**。上游作为只读依赖，独立升级 |
| 个人代码放哪？ | 独立 `personal/` 包，不修改上游文件 |
| 怎么读上游数据？ | 优先 **只读数据库 + REST API + 文件契约** |
| 怎么影响报告？ | 优先 **后处理增强**（读上游 JSON，生成个人报告）；Prompt 注入作为可选补丁 |
| 插件怎么做？ | 自定义 `Plugin` 协议 + manifest + registry，插件只依赖 `personal/contracts`，不依赖上游内部模块 |
| 回测怎么做？ | 独立组合回测引擎，A 股规则/成本内置；支持“信号回放”和“策略回测”两种模式 |
| QMT 怎么接？ | Windows 独立 `qmt-bridge` 服务，macOS 通过 HTTP 调用；交易与主程序隔离 |
| 数据存哪？ | 个人独立 SQLite（后续可换 Postgres），与上游数据库分离 |
| 上游升级怎么办？ | `git fetch upstream` + 契约测试 + 冒烟测试；个人代码零冲突或极少冲突 |

---

## 1. 设计原则

1. **Upstream-first, not fork-first**
   上游负责它擅长的：AI 分析、报告、Web/Bot、告警、选股、通知。个人层只补它不做的：数据质量、组合回测、基金分析、交易日志、QMT 执行、期权。

2. **只读上游，写自己的库**
   不写上游表、不改上游 schema、不 monkey patch 上游模块。个人层通过契约读取上游数据。

3. **契约优先**
   所有跨层交互都经过 `personal/contracts/`：Pydantic 模型 + 只读 SQL + API client。上游变化只影响契约层。

4. **插件只依赖稳定 API**
   插件不得 `import src.analyzer`、`import src.core.pipeline` 等内部模块；只能依赖 `personal.plugin_api` 暴露的协议与数据结构。

5. **分析可失败，交易必须安全**
   数据/分析/报告失败 → 降级、告警、继续；交易失败 → 拒绝、回滚、人工确认、对账。

6. **一切可追溯**
   每条数据有 `source / quality / ingested_at`；每次回测有 `run_id / data_version / cost_version / engine_version`；每笔交易有 `order_id / idempotency_key / audit log`。

7. **小补丁，可重放**
   如果必须改上游，补丁放在 `patches/`，每个补丁对应一个明确锚点，CI 验证可应用；升级失败就显式报错，不静默漂移。

8. **先 SQLite，后 Postgres**
   个人单机先用 SQLite（WAL）；数据量/并发上来再切 Postgres，存储层用 Repository 隔离。

---

## 2. 现状与约束

### 2.1 上游可复用的能力

| 能力 | 上游模块 | 个人层如何使用 |
|---|---|---|
| AI 分析报告 | `src/analyzer.py`、`src/core/pipeline.py` | 只读 `analysis_history` / API，后处理增强 |
| 组合账本 | `src/services/portfolio_service.py`、`portfolio_repo.py` | 只读快照/流水，个人层做风险与复盘 |
| 告警 | `src/services/alert_service.py` | 复用通知渠道；个人层可加数据质量告警 |
| 选股 | `src/services/screening/*` | 复用候选池；个人层做因子验证 |
| ETF 轮动 | `src/core/etf_rotation.py` | 作为组合回测参考实现，抽取通用引擎 |
| 通知 | `src/notification.py`、`notification_sender/*` | 复用；个人报告可走 webhook |
| Web/API | `api/v1/*` | 只读调用；个人层有自己的 FastAPI |

### 2.2 上游的扩展点（无需改代码）

- 策略 YAML：`strategies/*.yaml` + `AGENT_SKILL_DIR`
- 选股 YAML：`src/services/screening/strategies/*.yaml` + `STRATEGIES_DIR`
- 报告模板：`REPORT_RENDERER_ENABLED` + `REPORT_TEMPLATES_DIR`
- 自定义通知：`CUSTOM_WEBHOOK_URLS` + `CUSTOM_WEBHOOK_BODY_TEMPLATE`
- LLM：LiteLLM 兼容接口

### 2.3 约束

- 上游更新频繁（月均一个 minor release，日均 commit），**深度 fork 不可持续**。
- 上游没有正式插件系统；指标注入 Prompt 需要改 `analyzer._format_prompt`（因此默认不做）。
- QMT/xtquant **仅 Windows**；当前开发机是 macOS。
- 上游默认 SQLite；个人层独立 SQLite，避免锁竞争。
- 免费数据源不稳定；付费 Tushare 5000 积分作为稳定主源，AkShare/BaoStock 兜底。

---

## 3. 总体架构

```text
┌──────────────────────────────────────────────────────────────┐
│                    Upstream DSA（只读依赖）                    │
│  pipeline / analyzer / web / bot / alerts / screening         │
│  DB: data/stock_analysis.db（只读）   API: /api/v1/*（只读）    │
└───────────────────────────┬──────────────────────────────────┘
                            │  contracts/（只读 SQL / API / 文件）
┌───────────────────────────▼──────────────────────────────────┐
│                Personal Layer（本方案，独立进程）               │
│                                                              │
│  contracts/   上游 DB 视图、API client、Pydantic 模型           │
│  datahub/     采集、标准化、复权、交易性标记、质量校验、存储       │
│  analytics/   自定义指标、基金指标、组合风险                      │
│  backtest/    组合回测、成本模型、基准、归因、统计                 │
│  journal/     交易日志、复盘、错误分类                           │
│  reporting/   个人报告（HTML/PDF/Markdown）、通知                 │
│  plugins/     插件 SDK、registry、loader、内置示例                │
│  execution/   QMT 客户端（调 Windows bridge）                    │
│  api/         个人 FastAPI（可选）                               │
│  cli/         命令行入口                                        │
│                                                              │
│  DB: data/personal.db（读写）                                   │
└───────────────┬──────────────────────────────┬────────────────┘
                │ HTTP + Token                  │ HTTP + Token
┌───────────────▼──────────────┐  ┌────────────▼────────────────┐
│ Windows qmt-bridge           │  │ 数据源                       │
│ FastAPI + xtquant            │  │ Tushare / AkShare / BaoStock │
│ QMT/miniQMT 客户端（登录）     │  │ 天天基金 / 交易所             │
└──────────────────────────────┘  └─────────────────────────────┘
```

### 3.1 进程边界

| 进程 | 运行位置 | 职责 | 故障影响 |
|---|---|---|---|
| Upstream DSA | macOS/Linux/Windows | AI 分析、Web、告警 | 个人层降级为“仅数据/回测/复盘” |
| Personal Layer | macOS | 数据、回测、基金、日志、报告 | 不影响上游分析 |
| qmt-bridge | Windows | 行情、下单、查询、对账 | 个人层拒绝交易，分析不受影响 |
| Scheduler | macOS launchd/cron | 每日数据、报告、复盘 | 手动重跑 |

### 3.2 数据流

```text
数据源
  → datahub.ingest（拉取）
  → datahub.normalize（统一 schema/单位/代码）
  → datahub.quality（跨源校验/异常标记）
  → datahub.adjust（复权因子）
  → datahub.tradability（停牌/ST/涨跌停）
  → personal.db
  → analytics（指标/基金/组合）
  → backtest / journal / reporting
  → 通知（webhook/邮件）或个人 Web
```

上游数据流：

```text
Upstream DB/API
  → contracts.upstream（只读）
  → personal.db（快照/物化视图）
  → 个人报告/复盘/风控
```

---

## 4. 仓库结构

```text
daily_stock_analysis/                 # 个人工作区（顶层）
├── upstream/                         # 上游只读克隆（不提交个人改动）
│   └── ...                           # git remote = ZhuLinsen/daily_stock_analysis
├── personal/                         # 个人扩展层（本方案）
│   ├── __init__.py
│   ├── config.py                     # Pydantic Settings
│   ├── contracts/
│   │   ├── upstream_db.py            # 只读 SQL / 视图
│   │   ├── upstream_api.py           # REST client
│   │   ├── models.py                 # 跨层 Pydantic 模型
│   │   └── version.py                # 上游版本/能力探测
│   ├── datahub/
│   │   ├── sources/                  # tushare/akshare/baostock/qmt/fund
│   │   ├── normalize.py
│   │   ├── quality.py
│   │   ├── adjust.py
│   │   ├── tradability.py
│   │   ├── store.py                  # Repository
│   │   └── sync.py                   # CLI: 增量/回填
│   ├── analytics/
│   │   ├── indicators.py
│   │   ├── fund.py
│   │   └── portfolio.py
│   ├── backtest/
│   │   ├── engine.py
│   │   ├── data_portal.py
│   │   ├── portfolio.py
│   │   ├── execution.py
│   │   ├── costs.py
│   │   ├── constraints.py
│   │   ├── metrics.py
│   │   ├── benchmark.py
│   │   └── report.py
│   ├── journal/
│   │   ├── models.py
│   │   ├── service.py
│   │   └── review.py
│   ├── reporting/
│   │   ├── renderer.py
│   │   └── templates/
│   ├── execution/
│   │   ├── qmt_client.py             # macOS 侧 HTTP client
│   │   ├── risk.py                   # 本地事前风控
│   │   └── reconcile.py
│   ├── plugins/
│   │   ├── api.py                    # 插件协议（稳定）
│   │   ├── manifest.py
│   │   ├── registry.py
│   │   ├── loader.py
│   │   └── builtin/
│   │       └── obv.py
│   ├── api/                          # 可选：个人 FastAPI
│   ├── cli/
│   │   └── main.py
│   └── tests/
├── qmt-bridge/                       # Windows 独立服务
│   ├── app.py                        # FastAPI
│   ├── xtquant_adapter.py
│   ├── risk.py
│   ├── requirements.txt
│   └── README.md
├── patches/                          # 可选：上游最小补丁
├── config/
│   ├── personal.example.env
│   └── backtest.example.yaml
├── data/
│   ├── personal.db
│   └── cache/
├── scripts/
│   ├── sync_upstream.sh
│   ├── apply_patches.sh
│   ├── run_daily.sh
│   └── check_contracts.py
└── docs/
    └── PERSONAL_EXTENSION_ARCHITECTURE.md
```

### 4.1 上游目录管理

三种方式，推荐 **B**：

| 方式 | 优点 | 缺点 | 建议 |
|---|---|---|---|
| A. git submodule | 版本固定清晰 | 个人仓库操作繁琐 | 可选 |
| B. `upstream/` 只读 clone + `UPSTREAM_VERSION` 文件 | 简单、可随时 pull | 需要脚本同步 | **推荐** |
| C. 直接 fork | 改代码方便 | 合并负担大 | 不推荐 |

`scripts/sync_upstream.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
cd upstream
git fetch origin --tags
git checkout main
git pull --ff-only origin main
git rev-parse HEAD > ../UPSTREAM_VERSION
cd ..
python scripts/check_contracts.py
```

---

## 5. 低耦合策略

### 5.1 四层隔离

```text
上游内部模块  ←禁止直接 import←  contracts  ←  personal 业务
                                      ↑
                              upstream DB/API/文件
```

1. **禁止**：`from src.analyzer import ...`、`from src.core.pipeline import ...`
2. **允许**：`personal.contracts.upstream_db` / `upstream_api` / `models`
3. **允许**：读取上游 SQLite（只读 URI）+ REST API + 导出的 JSON/Markdown
4. **禁止**：写上游表、改上游迁移、monkey patch

### 5.2 契约层

`personal/contracts/upstream_db.py`：

```python
from sqlalchemy import create_engine, text

class UpstreamDB:
    def __init__(self, path: str):
        # SQLite 只读打开，杜绝误写
        self.engine = create_engine(
            f"sqlite:///file:{path}?mode=ro&uri=true",
            connect_args={"uri": True},
        )

    def recent_analyses(self, code: str, limit: int = 50):
        sql = text("""
            SELECT id, query_id, code, name, sentiment_score,
                   operation_advice, trend_prediction, raw_result,
                   context_snapshot, created_at
            FROM analysis_history
            WHERE code = :code
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(sql, {"code": code, "limit": limit})]
```

`personal/contracts/models.py`：

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Any, Optional

class AnalysisRecord(BaseModel):
    id: int
    code: str
    name: Optional[str]
    sentiment_score: Optional[int]
    operation_advice: Optional[str]
    trend_prediction: Optional[str]
    raw_result: Optional[dict[str, Any]]
    created_at: datetime
```

`personal/contracts/version.py`：

```python
REQUIRED_UPSTREAM_TABLES = {
    "analysis_history": {"id", "code", "raw_result", "created_at"},
    "portfolio_account": {"id", "base_currency"},
    "portfolio_trade": {"account_id", "symbol", "side", "quantity", "price"},
}

def check(engine) -> list[str]:
    """返回缺失的表/字段，启动时调用；缺失则进入降级模式。"""
```

### 5.3 上游升级流程

```text
1. scripts/sync_upstream.sh
2. pytest personal/tests/contracts
3. python scripts/check_contracts.py
4. pytest personal/tests
5. 手工冒烟：读 1 份上游报告 + 跑 1 次回测 + 生成 1 份个人报告
6. 打 tag：personal-vX.Y.Z（记录 UPSTREAM_VERSION）
```

**契约测试**是核心：上游改 schema/API，测试先失败，而不是运行时才发现。

### 5.4 补丁管理（最后手段）

只有“必须让自定义指标进入上游 Prompt”时才用：

```text
patches/
  0001-inject-personal-context.patch
```

规则：
- 每个补丁只改一个函数/一个锚点；
- 补丁头部写明 `Upstream-Version: v3.34.0`；
- `scripts/apply_patches.sh` 先 `git apply --check`，失败即中止；
- CI 对 pinned upstream 跑一遍补丁 + 测试；
- 上游若已原生支持，删除补丁。

### 5.5 版本与能力探测

```python
# personal/contracts/version.py
FEATURES = {
    "analysis_context_pack": "context_snapshot" in columns("analysis_history"),
    "portfolio_lots": table_exists("portfolio_position_lot"),
    "decision_signals": table_exists("decision_signals"),
}
```

个人层按能力分支，不按版本号硬编码。

---

## 6. 插件架构

### 6.1 插件类型

| 类型 | 用途 | 依赖 |
|---|---|---|
| `indicator` | 自定义指标计算与摘要 | `personal.plugin_api` |
| `fund_metric` | 基金/ETF 指标 | 同上 |
| `report_section` | 个人报告段落 | 同上 |
| `data_source` | 新数据源适配 | `DataProvider` 协议 |
| `strategy` | 回测策略 | `Strategy` 协议 |
| `execution_adapter` | 券商执行适配 | `ExecutionAdapter` 协议 |
| `journal_hook` | 交易日志钩子 | `JournalHook` 协议 |

### 6.2 Manifest

`plugins/obv/plugin.yaml`：

```yaml
api_version: "1.0"
name: obv
version: "0.1.0"
type: indicator
display_name: OBV 能量潮
entry: plugin:OBVIndicator
requires:
  personal: ">=0.1.0"
  upstream: ">=3.34,<4"
permissions:
  - market_data:read
config_schema:
  window:
    type: integer
    default: 20
    minimum: 2
    maximum: 250
```

### 6.3 稳定插件 API

`personal/plugins/api.py`（插件唯一允许 import 的模块）：

```python
from typing import Any, Mapping, Protocol
import pandas as pd

PLUGIN_API_VERSION = "1.0"

class PluginContext(Protocol):
    config: Mapping[str, Any]
    logger: Any
    def get_bars(self, code: str, days: int) -> pd.DataFrame: ...

class IndicatorPlugin(Protocol):
    name: str
    version: str
    required_columns: tuple[str, ...]
    def compute(self, df: pd.DataFrame, params: Mapping[str, Any]) -> pd.DataFrame: ...
    def summarize(self, df: pd.DataFrame, params: Mapping[str, Any]) -> dict[str, Any]: ...
    def render(self, summary: dict[str, Any], *, language: str) -> str: ...

class StrategyPlugin(Protocol):
    name: str
    def generate_targets(self, ctx: Any, date: pd.Timestamp) -> dict[str, float]: ...
```

**关键约束**：插件 API 只暴露 pandas DataFrame、dict、基本类型和你自己的 Protocol；不暴露上游类。

### 6.4 Registry / Loader / 生命周期

```python
class PluginRegistry:
    def __init__(self): self._items = {}
    def register(self, plugin, manifest): ...
    def get(self, name: str): ...
    def all(self, type_: str): ...

def discover(plugin_dirs: list[Path], allowlist: set[str] | None):
    # 1) entry_points(group="dsa.personal.plugins")
    # 2) plugin_dirs/*/plugin.yaml
    # 3) 校验 api_version / requires / permissions
```

生命周期：

```text
discover → validate manifest → import entry → instantiate
→ init(context) → health_check → enabled
→ on hook (try/except + timeout) → disabled/unload
```

错误隔离：
- 单插件异常 → 记录 `plugin_error`，跳过该插件，主流程继续；
- 单插件超时 → 默认 2s（指标）/10s（策略），可配；
- 输出大小上限 → 防止 Prompt/报告膨胀；
- 禁止插件写上游 DB。

### 6.5 配置

```env
PERSONAL_PLUGINS_ENABLED=true
PERSONAL_PLUGIN_DIRS=./plugins
PERSONAL_PLUGIN_ALLOWLIST=obv,atr
PERSONAL_PLUGIN_TIMEOUT_MS=2000
```

### 6.6 与上游的关系

- 插件运行在 **Personal Layer**，不注入上游进程。
- 需要影响上游报告时，采用 **后处理**：读上游 `raw_result`，在个人报告里追加插件段落。
- 只有“必须进入 LLM Prompt”时，才用 `patches/0001` 注入 `custom_context`，且默认关闭。

---

## 7. 数据层设计

### 7.1 模块职责

| 模块 | 职责 |
|---|---|
| `sources/` | 拉取原始数据；每个源实现 `fetch_*`，失败抛统一异常 |
| `normalize` | 代码/市场/单位/时区/列名统一 |
| `quality` | 跨源校验、缺失、重复、异常、stale |
| `adjust` | 复权因子、总收益序列 |
| `tradability` | 停牌、ST、涨跌停、上市天数、T+1 |
| `store` | upsert、查询、分区、索引 |
| `sync` | 增量/回填/重算 CLI |

### 7.2 规范化代码

```text
A 股: 600519 → 600519.SH, 000001 → 000001.SZ, 920493 → 920493.BJ
ETF: 510050 → 510050.SH, 159915 → 159915.SZ
基金: 000001.OF（场外）
期权: 510050C2611A03000（示例，按交易所规则）
```

### 7.3 核心表（SQLite DDL 草案）

```sql
CREATE TABLE instrument (
  code TEXT PRIMARY KEY,
  name TEXT,
  market TEXT NOT NULL,          -- cn/hk/us
  asset_type TEXT NOT NULL,      -- stock/etf/fund/option
  lot_size INTEGER DEFAULT 100,
  tick_size REAL DEFAULT 0.01,
  currency TEXT DEFAULT 'CNY',
  status TEXT DEFAULT 'active',
  updated_at TEXT NOT NULL
);

CREATE TABLE daily_bar (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL,
  volume REAL, amount REAL,
  source TEXT NOT NULL,
  quality TEXT DEFAULT 'ok',
  ingested_at TEXT NOT NULL,
  PRIMARY KEY (code, trade_date, source)
);

CREATE TABLE adjust_factor (
  code TEXT NOT NULL,
  ex_date TEXT NOT NULL,
  factor REAL NOT NULL,
  reason TEXT,                   -- dividend/split/rights
  source TEXT NOT NULL,
  PRIMARY KEY (code, ex_date, source)
);

CREATE TABLE trading_status (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  is_suspended INTEGER DEFAULT 0,
  is_st INTEGER DEFAULT 0,
  limit_up REAL, limit_down REAL,
  is_limit_up INTEGER DEFAULT 0,
  is_limit_down INTEGER DEFAULT 0,
  source TEXT NOT NULL,
  PRIMARY KEY (code, trade_date)
);

CREATE TABLE fund_nav (
  code TEXT NOT NULL,
  nav_date TEXT NOT NULL,
  nav REAL, acc_nav REAL, adj_nav REAL,
  source TEXT NOT NULL,
  PRIMARY KEY (code, nav_date, source)
);

CREATE TABLE fund_holding (
  code TEXT NOT NULL,
  report_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  weight REAL, shares REAL, market_value REAL,
  source TEXT NOT NULL,
  PRIMARY KEY (code, report_date, symbol)
);

CREATE TABLE etf_snapshot (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  iopv REAL, close REAL, premium_pct REAL,
  volume REAL, amount REAL,
  source TEXT NOT NULL,
  PRIMARY KEY (code, trade_date, source)
);

CREATE TABLE data_quality_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset TEXT NOT NULL,
  code TEXT, trade_date TEXT,
  rule TEXT NOT NULL,
  severity TEXT NOT NULL,        -- info/warn/error
  detail TEXT,
  created_at TEXT NOT NULL
);
```

### 7.4 质量规则

| 规则 | 阈值 | 动作 |
|---|---|---|
| 收盘价跨源偏差 | > 0.5% | warn，标记 quality |
| 成交量跨源偏差 | > 20% | warn，标记 |
| OHLC 非法 | high < max(open, close) 等 | error，丢弃该源 |
| 日期缺失 | 交易日历应有但无 | warn，标记 stale |
| 重复记录 | 同源同日多条 | error，去重 |
| 极端跳空 | 非除权日 > 20% | warn，人工复核 |
| 单位异常 | 成交量/成交额比例异常 | warn，检查手/股 |

### 7.5 数据源优先级

```text
日线/复权/停牌/涨跌停：Tushare → BaoStock → AkShare → 腾讯
基金净值/持仓：Tushare → AkShare/天天基金
ETF IOPV：AkShare/东财 → QMT
实时行情：QMT → 腾讯/新浪 → AkShare
期权日频：交易所 → AkShare → Tushare
```

每次落库记录 `source`，不覆盖不同源；查询时按优先级选取。

### 7.6 幂等与版本

- 所有表 `PRIMARY KEY` 含 `source` 或唯一键；`INSERT ... ON CONFLICT DO UPDATE`。
- 派生数据带 `calc_version`（如 `adj-v1`、`indicator-v1`）。
- 回测记录 `data_version`（个人库快照日期 + 上游版本）。

---

## 8. 组合回测引擎

### 8.1 两种模式

| 模式 | 输入 | 用途 |
|---|---|---|
| **Signal Replay** | 上游 `analysis_history` / `decision_signals` | 评估 AI 建议的真实组合收益 |
| **Strategy Backtest** | 插件策略 / YAML 规则 / 因子 | 验证自己的选股/轮动策略 |

### 8.2 组件

```text
DataPortal ──► Strategy ──► TargetWeights
     │                           │
     ▼                           ▼
TradingCalendar          ConstraintEngine
     │                           │
     ▼                           ▼
ExecutionSimulator ◄──── CostModel
     │
     ▼
Portfolio（cash/lots/realized/unrealized）
     │
     ▼
Metrics + Benchmark + Attribution + Report
```

### 8.3 A 股规则矩阵

| 规则 | 实现 |
|---|---|
| T+1 | 买入日 < 卖出日才允许卖 |
| 100 股整数倍 | 买入数量向下取整到 100 |
| 涨跌停 | 涨停不买、跌停不卖（可配“允许排队”） |
| 停牌 | 不成交 |
| ST | 默认排除，可配 |
| 佣金 | 万 2.5，最低 5 元 |
| 印花税 | 卖出 0.05%（ETF 免） |
| 过户费 | 0.001% 双向 |
| 滑点 | 固定 bp 或按成交额/ADV |
| 分红税 | 持有期 ≤1 月 20%、1 月~1 年 10%、>1 年 0 |
| 基金申赎费 | 按持有期/份额类别 |
| 基准 | 沪深 300/中证 500/中证 1000/自定义 |

### 8.4 成本模型接口

```python
class CostModel(Protocol):
    def buy_cost(self, amount: float, code: str) -> float: ...
    def sell_cost(self, amount: float, code: str, holding_days: int) -> float: ...
    def slippage(self, price: float, side: str, amount: float) -> float: ...
```

### 8.5 指标

- 收益：累计、年化、年度
- 风险：年化波动、最大回撤、Calmar、下行波动、VaR（可选）
- 风险调整：Sharpe、Sortino、Information Ratio
- 交易：换手率、胜率、盈亏比、平均持仓天数、成本占比
- 信号：MAE、MFE、方向准确率、样本量、置信区间
- 归因：行业/个股/择时（简化 Brinson）

### 8.6 配置示例

```yaml
# config/backtest.example.yaml
mode: signal_replay          # signal_replay | strategy
start: "2023-01-01"
end: "2026-11-12"
initial_cash: 1000000
benchmark: "000300.SH"
cost:
  commission_bps: 2.5
  min_commission: 5
  stamp_duty_sell_bps: 5
  transfer_fee_bps: 0.1
  slippage_bps: 5
constraints:
  max_position_pct: 10
  max_sector_pct: 30
  max_positions: 10
  exclude_st: true
  exclude_suspended: true
```

### 8.7 统计严谨性

- 样本 < 30：只展示计数，不给“胜率”结论。
- 输出 Wilson 置信区间。
- 参数扫描 + Walk-forward（训练/验证/测试）。
- 成本压力测试：成本 ×1 / ×2 / ×3。

---

## 9. 基金分析模块

### 9.1 指标

| 类别 | 指标 |
|---|---|
| 收益 | 区间收益、年化、年度、相对基准 |
| 风险 | 最大回撤、波动率、下行波动、Calmar |
| 风险调整 | Sharpe、Sortino、Information Ratio |
| ETF | IOPV、折溢价、跟踪误差、日均成交额、买卖价差 |
| 持仓 | 前十大、行业分布、集中度、换手、风格漂移 |
| 管理人 | 任期、变更、管理规模、同类排名 |
| 费率 | 管理费、托管费、申购/赎回费、销售服务费 |
| 组合 | 基金间重叠度、股票+基金合并暴露 |

### 9.2 数据

- 场外基金：`fund_nav`、`fund_holding`（季报）、`fund_manager`、`fund_fee`
- ETF/LOF：`etf_snapshot`、`daily_bar`、`index_daily`
- 来源：Tushare、AkShare、天天基金、交易所

### 9.3 输出

- 基金记分卡（单只）
- 基金对比表（多只）
- 重叠度矩阵
- 组合 X-Ray（股票 + 基金合并行业/主题暴露）

---

## 10. 交易日志与复盘

### 10.1 表

```sql
CREATE TABLE trade_journal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  side TEXT NOT NULL,
  quantity REAL NOT NULL,
  price REAL NOT NULL,
  amount REAL NOT NULL,
  reason TEXT,
  analysis_id INTEGER,             -- 关联上游 analysis_history.id
  decision_signal_id INTEGER,
  order_id TEXT,
  stop_loss REAL, target_price REAL,
  mistake_type TEXT,               -- 追高/过早止盈/未止损/听消息/仓位过重
  notes TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE trade_review (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period TEXT NOT NULL,            -- day/week/month
  start_date TEXT, end_date TEXT,
  pnl REAL, benchmark_return REAL, excess_return REAL,
  win_rate REAL, max_drawdown REAL,
  summary TEXT,
  created_at TEXT NOT NULL
);
```

### 10.2 流程

```text
盘前计划 → 上游分析/个人信号 → 人工确认
→ 下单（QMT/手动）→ 成交回填
→ 交易日志 → 日/周/月复盘 → 错误分类 → 规则迭代
```

### 10.3 报告

- 每日：持仓盈亏、异动、公告、明日事件
- 每周：相对基准、行业/个股归因、胜率、回撤、仓位
- 每月：策略有效性、错误分类、下月计划

---

## 11. QMT 执行桥

### 11.1 边界

- QMT/xtquant **只在 Windows** 运行。
- `qmt-bridge` 是独立服务，不导入个人层代码。
- macOS 侧只通过 HTTP + Token 调用。
- **默认只读/模拟**；实盘需显式开关 + 二次确认。

### 11.2 API

```text
GET  /health
GET  /quote?codes=600519.SH,510050.SH
GET  /positions
GET  /orders
POST /orders                  # 下单
POST /orders/{id}/cancel
GET  /trades
POST /reconcile
```

请求示例：

```json
{
  "account_id": "xxx",
  "code": "600519.SH",
  "side": "buy",
  "quantity": 100,
  "price_type": "limit",
  "price": 1500.0,
  "idempotency_key": "20261112-600519-buy-001",
  "strategy": "dsa_signal",
  "remark": "analysis_id=12345"
}
```

### 11.3 订单状态机

```text
NEW → SUBMITTED → PARTIAL → FILLED
                 ├→ CANCELLED
                 └→ REJECTED
```

- `idempotency_key` 唯一；重复请求返回原订单。
- 超时/断线：先查询，不盲目重试。
- 每日对账：QMT 持仓/成交 vs 个人 `trade_journal` vs 上游组合快照。

### 11.4 本地事前风控（macOS 侧 + bridge 侧双保险）

- 代码白名单（仅 A 股/ETF/已开通期权）
- 单笔最大金额、单日最大下单次数
- 仓位上限、行业上限
- 涨跌停/停牌检查
- T+1 检查
- 100 股整数倍
- 交易时段检查
- 人工确认开关（默认开启）

### 11.5 安全

- 仅监听 `127.0.0.1` 或内网；防火墙限制。
- Bearer Token；可选 HMAC 签名。
- 不记录完整账号/密码；日志脱敏。
- 独立 Windows 账户/虚拟机，不放公网。

---

## 12. 期权扩展（预留，不在 MVP）

### 12.1 数据模型

```sql
CREATE TABLE option_contract (
  code TEXT PRIMARY KEY,
  underlying TEXT NOT NULL,
  expiry TEXT NOT NULL,
  strike REAL NOT NULL,
  option_type TEXT NOT NULL,       -- call/put
  multiplier INTEGER DEFAULT 10000,
  settlement TEXT DEFAULT 'european',
  exchange TEXT
);

CREATE TABLE option_quote (
  code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  last REAL, bid REAL, ask REAL,
  volume REAL, open_interest REAL,
  iv REAL,
  delta REAL, gamma REAL, vega REAL, theta REAL,
  source TEXT NOT NULL,
  PRIMARY KEY (code, trade_date, source)
);
```

### 12.2 功能

- 期权链、IV 曲面、Greeks
- BS（欧式 ETF 期权）/ 二叉树（美式）
- 策略模板：备兑、保护性认沽、领口、价差、跨式
- 盈亏图、最大亏损、保证金、到期行权
- 组合 Greeks 聚合、情景压力
- 回测：合约乘数、流动性、买卖价差、行权交收

### 12.3 触发条件

- 期权账户开通 + QMT 期权权限确认
- 先模拟盘 1~2 个月
- 独立 `personal/options/` 模块，不影响股票/基金 MVP

---

## 13. 配置与环境

### 13.1 依赖

```text
Python 3.11+
pandas / numpy / pydantic / pydantic-settings
sqlalchemy
httpx
fastapi / uvicorn（个人 API / bridge）
jinja2（报告）
akshare / tushare / baostock
pytest / pytest-cov
ruff / mypy（可选）
```

### 13.2 配置示例

```env
# 上游
PERSONAL_UPSTREAM_DB=./upstream/data/stock_analysis.db
PERSONAL_UPSTREAM_API=http://127.0.0.1:8000
PERSONAL_UPSTREAM_TIMEOUT=30

# 个人库
PERSONAL_DB=./data/personal.db
PERSONAL_DATA_DIR=./data

# 数据源
TUSHARE_TOKEN=xxx
PERSONAL_DATA_SOURCE_PRIORITY=tushare,baostock,akshare,tencent

# 回测
PERSONAL_BACKTEST_COST_VERSION=cn-a-v1
PERSONAL_BACKTEST_DEFAULT_BENCHMARK=000300.SH

# QMT
QMT_BRIDGE_URL=http://192.168.1.50:8710
QMT_BRIDGE_TOKEN=xxx
QMT_TRADING_ENABLED=false
QMT_REQUIRE_CONFIRM=true

# 插件
PERSONAL_PLUGINS_ENABLED=true
PERSONAL_PLUGIN_DIRS=./plugins
PERSONAL_PLUGIN_ALLOWLIST=obv,atr
```

---

## 14. 可观测性与运维

- **日志**：JSON lines，字段 `ts/level/run_id/component/dataset/code/source/quality/message`。
- **指标**：采集成功/失败、行数、耗时、质量告警数、回测耗时、下单延迟、拒单数。
- **看板**：`personal status` CLI + HTML 日报；需要时再接 Grafana。
- **告警**：数据 stale、源连续失败、质量 error、对账差异、订单拒绝。
- **备份**：`personal.db` 每日备份；`config/` 与 `plugins/` 版本化；上游 DB 只读备份。
- **调度**：macOS `launchd` 或 cron；Windows 任务计划程序跑 bridge。

---

## 15. 测试策略

| 层级 | 内容 |
|---|---|
| 单元 | 成本模型、复权、交易性、指标、组合会计 |
| 契约 | 上游表/字段/API schema；fixtures |
| Golden | 小样本数据 + 已知结果，防回归 |
| 集成 | 数据同步 → 回测 → 报告 全链路 |
| QMT Mock | 下单/撤单/查询/对账；断线重连 |
| 上游漂移 | pinned upstream 跑契约测试 + 冒烟 |
| 属性测试 | 现金 + 持仓 = 净值；无负现金（非两融）；T+1 不违规 |
| 性能 | 10 年 × 5000 股票日线回测 < 目标时间 |

---

## 16. 实施路线

### Phase 0：脚手架与契约（2~3 天）

- `personal/` 包、配置、日志、CLI
- 上游只读 DB/API 契约
- `scripts/sync_upstream.sh`、`check_contracts.py`
- CI / pre-commit
- **验收**：能读取上游最近 10 条分析；契约测试通过

### Phase 1：数据质量 + 回测（1~2 周）

- 复权因子、停牌/ST/涨跌停、跨源校验
- 成本模型、A 股交易约束
- Signal Replay 组合回测 + 基准 + MAE/MFE + 置信区间
- **验收**：同一批上游信号，扣成本前后收益差异可见；回测可复现（run_id）

### Phase 2：基金 + 日志 + 复盘（1~2 周）

- 基金净值/折溢价/跟踪误差/持仓/费率
- 交易日志、日/周/月复盘
- 个人报告模板
- **验收**：基金记分卡、重叠度矩阵、周报可生成

### Phase 3：QMT 桥 + 模拟盘（1 周）

- Windows bridge、xtquant 适配、订单状态机、对账
- macOS client、本地风控、人工确认
- **验收**：模拟盘下单/撤单/查询/对账通过；断线可恢复

### Phase 4：期权（开通后）

- 期权链、Greeks、策略模板、保证金、回测
- **验收**：模拟盘期权策略盈亏图与保证金计算正确

---

## 17. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 上游 schema/API 变化 | 个人层读取失败 | 契约测试 + 能力探测 + 适配器 |
| 上游更新频繁 | 合并冲突 | 不 fork；`personal/` 独立；补丁最少化 |
| 免费数据源失效 | 数据缺失 | 多源 fallback + 质量标记 + 告警 |
| 复权/停牌处理错误 | 回测失真 | Golden 测试 + 跨源校验 |
| 回测过拟合 | 虚假收益 | Walk-forward + 样本外 + 成本压力 |
| QMT 断线/拒单 | 交易失败 | 心跳/重连/幂等/对账/人工兜底 |
| QMT 仅 Windows | 部署复杂 | 独立 Windows VM/mini PC + 内网 bridge |
| 密钥/账户泄露 | 资金风险 | 本地/内网、Token、脱敏、独立账户 |
| 数据授权 | 合规风险 | 个人使用、不转售、遵守源条款 |
| 范围蔓延 | 延期 | 阶段门禁 + 非目标清单 |

---

## 18. ADR 摘要

| ADR | 决策 | 理由 |
|---|---|---|
| ADR-001 | 上游只读依赖，不 fork 核心 | 上游更新快，fork 不可持续 |
| ADR-002 | 个人独立数据库 | 避免 schema/写入冲突 |
| ADR-003 | 插件协议 + registry，不 monkey patch | 解耦、可测试、可禁用 |
| ADR-004 | 报告后处理优先，Prompt 补丁最后 | 零耦合，升级安全 |
| ADR-005 | QMT 独立 Windows bridge | 平台隔离、安全隔离 |
| ADR-006 | SQLite 先行，Postgres 可替换 | 个人规模足够，Repository 隔离 |
| ADR-007 | 回测分 Signal Replay / Strategy 两模式 | 分别评估 AI 建议与自有策略 |
| ADR-008 | 基金/期权独立模块 | 不污染股票主链路，按需启用 |

---

## 19. 需要你确认的 6 个决策点

1. **上游管理方式**：`upstream/` 只读 clone（推荐）还是 git submodule？
2. **数据库**：SQLite 先行（推荐）还是直接 Postgres？
3. **报告集成**：先做“后处理增强”（推荐，零补丁）还是直接改上游 Prompt？
4. **QMT 部署**：Windows 虚拟机 / 独立 mini PC / 云 Windows，选哪个？
5. **数据源预算**：Tushare 5000 积分（500 元/年）是否接受？
6. **是否回馈上游**：数据质量/成本模型/插件协议是否提 PR？

---

## 20. 非目标（明确不做）

- 不改上游核心分析/报告/Web 代码
- 不做机构级 RBAC/SSO/多租户/审批流
- 不做 OMS/EMS/FIX/TCA
- 不做多资产（债券/商品/FX/加密）
- 不做高频/Tick 级策略（除非后续单独立项）
- 不做自动下载/执行第三方插件
- 不做数据再分发

---

> 评审通过后，建议从 **Phase 0 + Phase 1** 开始，先打通“读上游 → 数据质量 → 成本回测”这条链路，再逐步加基金、日志、QMT。
