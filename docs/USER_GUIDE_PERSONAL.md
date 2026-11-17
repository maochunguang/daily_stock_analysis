# 个人扩展使用手册

> 面向**使用者**的操作手册：怎么打开、怎么点、每个字段什么意思、出错怎么办。
> 架构和边界看 [PERSONAL_EXTENSION_ARCHITECTURE.md](PERSONAL_EXTENSION_ARCHITECTURE.md)；
> 机器可读上下文看 [AI_CONTEXT.md](AI_CONTEXT.md)；变更历史看
> [CHANGELOG_PERSONAL.md](CHANGELOG_PERSONAL.md)。

| 项目 | 值 |
|---|---|
| 适用仓库 | `maochunguang/daily_stock_analysis`（自包含 fork） |
| 个人层版本 | `0.1.0` |
| 最后更新 | 2026-11-17 |
| 主要入口 | 集成 Web UI `/personal`、独立控制台、CLI |
| 数据范围 | A 股股票、ETF；基金净值/期权为后续阶段 |

---

## 0. 功能导航

| 我想做什么 | 入口 | 本手册章节 |
|---|---|---|
| 看个人层状态、数据覆盖、最近回测 | `/personal` → 总览 | §4.1 |
| 同步日线 / 复权因子 / 交易日历 / 交易状态 | `/personal` → 数据同步，或 `sync` | §4.2、§5 |
| 用合成数据验证回测流程 | `/personal` → 个人回测 → Demo | §4.3 |
| 用上游 AI 建议做组合回测 | `/personal` → 个人回测 → Replay | §4.3 |
| 看深度复盘（TRIN/期指/融资余额） | `/personal` → 深度复盘 | §4.6 |
| 导入/查看市场宽度（阿姆氏 TRIN） | `import-arms` + `breadth`，API `/api/market/breadth` | §5、§7.5 |
| 看已装插件 | `/personal` → 插件，或 `plugins` | §4.4、§8 |
| 检查 Windows QMT 桥 | `/personal` → QMT | §4.5、§9 |
| 部署到 NAS | Docker Compose | §2.2、[DOCKER_PERSONAL.md](DOCKER_PERSONAL.md) |
| 改配置 | `.env` / `config/personal.env` | §3 |
| 查指标口径 | — | §6 |
| 新增功能时怎么改文档 | — | §12 |

---

## 1. 这套功能是什么

在**不改上游业务代码**的前提下，个人层补四类能力：

1. **数据质量**：A 股日线入库、复权因子、停牌/ST/涨跌停标记、跨源校验。
2. **成本回测**：按 A 股真实规则（T+1、100 股整手、佣金最低 5 元、卖出印花税、滑点）做组合回测。
3. **扩展机制**：指标/策略插件、上游 AI 建议回放、自定义指标入口。
4. **执行预备**：Windows QMT 桥的只读健康检查（默认不下单）。

**能做的：**

- 把 Tushare / BaoStock / AkShare 的日线同步到个人库。
- 用上游 `analysis_history` / `decision_signals` 的买卖建议做组合回测。
- 用合成数据快速验证回测链路和页面是否正常。
- 以插件方式增加指标，不污染上游代码。

**暂时不能做的（Phase 2）：**

- 基金净值、溢价率、跟踪误差分析。
- 交易日志 UI、日报/周报/月报。
- 期权分析与组合希腊字母。
- 自动下单。QMT 桥目前只做状态检查，且必须显式开启。

---

## 2. 三种使用入口

| 入口 | 适合谁 | 启动方式 | 地址 |
|---|---|---|---|
| **集成 Web UI** | 日常使用（推荐） | `python main.py --webui` | `http://127.0.0.1:8000/personal` |
| **Docker / NAS** | 7×24 运行、远程访问 | `docker compose ... up -d server` | `http://NAS_IP:8000/personal` |
| **独立控制台** | 只想跑个人层、不装上游依赖 | `python -m personal.cli.main web` | `http://127.0.0.1:8765` |
| **CLI** | 脚本、定时任务、排查问题 | `python -m personal.cli.main ...` | — |

页面功能三套入口一致；集成 UI 与上游共用登录、主题和左侧栏。

### 2.1 集成 Web UI（推荐）

前置条件：

- 已安装上游依赖：`pip install -r requirements.txt`
- 前端：首次启动会自动构建（需要 Node 18+ / npm）；也可以手动
  `cd apps/dsa-web && npm ci && npm run build`。构建产物在 `static/`，
  已被 gitignore，不会提交到仓库。想关闭启动时自动构建可设
  `WEBUI_AUTO_BUILD=false`（此时必须已有产物）。
- `PERSONAL_API_ENABLED=true`（默认）

启动：

```bash
# 仓库根目录
python main.py --webui
# 或
scripts/start_webui.sh
```

打开 `http://127.0.0.1:8000/personal`，左侧栏应出现「个人扩展」。

### 2.2 Docker / NAS

```bash
cp .env.example .env          # 首次
docker compose -f docker/docker-compose.yml build server
docker compose -f docker/docker-compose.yml up -d server
```

- 页面：`http://NAS_IP:8000/personal`
- 端口被占用时：`API_PORT=8010 docker compose -f docker/docker-compose.yml up -d server`
- 首次构建约 10 分钟（`wkhtmltopdf` + pip 依赖），镜像约 2.4GB
- 详细 NAS 说明（卷、SQLite、ARM64、认证、备份）见 [DOCKER_PERSONAL.md](DOCKER_PERSONAL.md)

> QMT 桥是 Windows-only，**不能**跑在 NAS 容器里；NAS 只做数据、回测和页面。

### 2.3 独立控制台

只依赖 `pandas/numpy/PyYAML/fastapi/uvicorn`，不需要上游整套依赖：

```bash
python -m personal.cli.main web --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765`。默认只监听本机，**没有登录**，不要直接暴露到公网。

### 2.4 CLI

```bash
python -m personal.cli.main info
```

如果已经通过开发工作区的 `pyproject.toml` 安装过，也可以直接用 `dsa-personal` 命令；
在自包含 fork 中推荐统一用 `python -m personal.cli.main`。

---

## 3. 配置

### 3.1 配置文件与优先级

个人层按以下顺序读取，**先读到的不被覆盖**：

1. 进程环境变量（Docker Compose 的 `environment` 最高）
2. `config/personal.env`（本地私有，已 gitignore）
3. `.env`（上游配置）

推荐做法：

- 本地开发：`cp config/personal.example.env config/personal.env`，只改这个文件。
- Docker/NAS：直接写 `.env` 或 Compose 的 `environment`。
- **不要提交** `config/personal.env`、`.env`、`data/*.db`。

### 3.2 常用变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PERSONAL_API_ENABLED` | `true` | 是否在 `/personal-api` 挂载个人 API |
| `PERSONAL_STOCK_LIST` | 空 | 默认股票池，逗号分隔，如 `600519,000001,510050` |
| `TUSHARE_TOKEN` | 空 | Tushare token；只在本地 env 文件里填 |
| `PERSONAL_DATA_SOURCE_PRIORITY` | `tushare,baostock,akshare,tencent` | 自动模式的优先级；`tencent` 目前未实现，会被跳过 |
| `DEEPSEEK_SEARCH_API_KEYS` | 空 | DeepSeek 官方网页搜索密钥（上游 AI 报告的新闻搜索用，与 LLM 的 `DEEPSEEK_API_KEYS` 相互独立），在 Web 设置页「数据源」分类里配置 |
| `PERSONAL_DB` | `data/personal.db` | 个人库路径；Docker 内为 `/app/data/personal.db` |
| `PERSONAL_UPSTREAM_DB` | `data/stock_analysis.db` | 上游库**只读**；Docker 内为 `/app/data/stock_analysis.db` |
| `PERSONAL_DATA_DIR` | `data` | 数据目录 |
| `PERSONAL_PLUGINS_ENABLED` | `true` | 是否启用插件 |
| `PERSONAL_PLUGIN_DIRS` | `plugins` | 插件目录，可逗号分隔多个 |
| `PERSONAL_PLUGIN_ALLOWLIST` | 空 | 只加载列出的插件名；空表示全部 |
| `PERSONAL_BACKTEST_INITIAL_CASH` | `1000000` | 回测初始资金 |
| `PERSONAL_BACKTEST_BENCHMARK` | `000300.SH` | 基准；留空则不算基准/超额 |
| `PERSONAL_BACKTEST_ADJUST` | `hfq` | 回测复权模式：`hfq` / `qfq` / `none` |
| `PERSONAL_CROSS_SOURCE_CHECK` | `true` | 同步时是否用第二个数据源交叉校验 |
| `PERSONAL_LOG_LEVEL` | `INFO` | 日志级别 |
| `QMT_BRIDGE_URL` | `http://127.0.0.1:8710` | Windows QMT 桥地址 |
| `QMT_BRIDGE_TOKEN` | 空 | 桥的 Bearer token |
| `QMT_TRADING_ENABLED` | `false` | 交易总开关，保持 false |
| `QMT_REQUIRE_CONFIRM` | `true` | 下单二次确认，保持 true |

### 3.3 股票池

- 同步时页面填「代码」或 CLI 传 `--code`，优先于 `PERSONAL_STOCK_LIST`。
- 代码格式宽松：`600519`、`sh600519`、`600519.SH`、`SZ000001` 都可。
- 归一化规则：`6` 开头 → `.SH`；`0/3` 开头 → `.SZ`；`4/8/9` 开头 → `.BJ`；
  `51/52/56/58` 开头 ETF → `.SH`，`15/16/18` 开头 → `.SZ`。

### 3.4 首次启动检查

```bash
python -m personal.cli.main info
```

重点看：

- `upstream db` 是否存在（不存在时 Replay 不可用）。
- `personal db` 路径是否是预期位置。
- `plugins: 1 loaded, 0 failed`。

---

## 4. 页面操作手册

页面顶部有「刷新」；五个标签：**总览 / 数据同步 / 个人回测 / 插件 / QMT**。
右上角可切换主题和语言（中/英）。

### 4.1 总览

| 区块 | 内容 | 怎么读 |
|---|---|---|
| 上游 DSA | `已连接` / `未生成` | 上游库不存在时显示「未生成」，跑一次上游分析即可 |
| 个人库 | 代码数 / 数据源数 / bar 数 | 数据同步后应增长 |
| 插件 | 已加载数量 + 名称 | 与「插件」标签一致 |
| QMT 桥 | `只读/未启用` 或 `交易已启用` | 后者只在 `QMT_TRADING_ENABLED=true` 时出现 |
| 数据覆盖 | Code / Source / Rows / Start / End | 每个代码当前生效的数据源 |
| 最近回测 | Run / Mode / Period / Return | 只显示保存过的回测 |
| 最近分析 | 上游最近的分析记录 | 上游库为空时给出提示 |
| 数据质量事件 | Rule / Severity / Detail | 同步时自动写入 |

> 「上游 DSA 未生成」不是故障。上游库 `data/stock_analysis.db` 只在第一次上游分析后创建。

### 4.2 数据同步

1. 选「数据集」：`日线 Bars`、`复权因子 Adjust`、`交易日历 Calendar` 或
   `交易状态 Status`。
2. 选「数据源」：`auto`、`synthetic`、`tushare`、`baostock`、`akshare`。
3. 填「代码」（逗号分隔）；留空则用 `PERSONAL_STOCK_LIST`（交易日历不需要代码）。
4. 填开始/结束日期；留空默认最近 **730 天**。
5. 按需勾选「跨源校验」（默认开启）。
6. 点「开始同步」，看「同步结果」。

推荐顺序：**交易日历 → 日线 → 复权因子 → 交易状态**。交易状态会用日历判断
停牌、用日线计算涨跌停；没有日历时会退化为只用已有日线。

结果字段：

| 字段 | 含义 |
|---|---|
| `code` | 归一化后的代码；日历为 `CALENDAR` |
| `source` | 实际成功的数据源；日历可能是 `derived`（从日线派生） |
| `rows` | 写入行数 |
| `quality_issues` | 单源质检问题数（已写入质量事件） |
| `cross_source_issues` | 与第二数据源的差异数（已写入质量事件） |
| `missing_days` | 日历中存在但没有日线的天数 |
| `suspended_days` | 交易状态同步时识别出的停牌天数 |
| `errors` | 各数据源失败原因（fallback 时会累积） |

数据源怎么选：

| 场景 | 建议 |
|---|---|
| 第一次验证链路 | `synthetic`（完全离线，不依赖网络） |
| A 股日线，有 Tushare token | `auto` 或 `tushare` |
| 没有 Tushare / 北交所 | `baostock`（不支持北交所） |
| ETF 日线 | Tushare 走 `fund_daily`；无权限时换 AkShare |
| 复权因子 | 目前只有 `tushare` 支持 |
| 交易日历 | BaoStock / AkShare / Tushare 任一可用；都失败时从已有日线派生 |
| 交易状态 | 由日历 + 日线 + 名称推导；`auto` 会先补日历，再按代码生成 |

> **跨源校验**：开启后，主源成功后会用第二个可用源抓同一区间做收盘价/成交量比对，
> 差异写入质量事件。它会让同步变慢、消耗额外请求；只想要速度时可在页面取消勾选，
> 或设 `PERSONAL_CROSS_SOURCE_CHECK=false`。

> 同步是**追加/覆盖同主键**：同一 `(code, trade_date, source)` 会更新，不会重复。
> 读取时只选**一个**数据源，不会把不同源的价格混在一起。

| 报错 | 原因 | 处理 |
|---|---|---|
| `Tushare ... 40203` | 免费积分无该接口权限 | 换 `baostock`，或升级 Tushare 积分 |
| `hourly rate limit reached` | `adj_factor` 免费档 1 次/小时 | 等一小时，或分批同步 |
| `no codes` | 没填代码且股票池为空 | 填代码或设 `PERSONAL_STOCK_LIST` |
| `BaoStock does not support BJ` | 北交所代码 | 换 Tushare/AkShare |

> 同步是**追加/覆盖同主键**：同一 `(code, trade_date, source)` 会更新，不会重复。
> 读取时只选**一个**数据源，不会把不同源的价格混在一起。

### 4.3 个人回测

#### Demo（合成数据）

用途：验证回测引擎、费用、T+1、页面渲染是否正常。**不是投资结论。**

1. 类型选 `Demo（合成数据）`。
2. 历史天数填 60–3000（默认 400）。
3. 需要留档就勾「保存到个人库」。
4. 点「运行」。

结果包含：绩效指标、净值曲线（策略 vs 基准）、交易明细（日期/代码/方向/数量/价格/费用/盈亏/原因）。

#### Replay（上游 AI 建议）

用途：把上游 `analysis_history.operation_advice` 和 `decision_signals.action` 变成买卖信号，
用真实（或已同步的）日线做组合回测。

1. 类型选 `Replay（上游 AI 建议）`。
2. 选「信号来源」：分析 + 决策信号 / 仅分析历史 / 仅决策信号。
3. 选日期范围。
4. 点「运行」。

前置条件：

- 上游库存在且有分析记录（否则提示「上游数据库不可用」）。
- 信号涉及的代码已经在个人库有日线（先做数据同步）。全部缺失会报
  `no local bars for signal codes; run ... sync first`；部分缺失的代码会被跳过。
- 回测默认使用**后复权**（`PERSONAL_BACKTEST_ADJUST=hfq`），分红送转不会造成假跌。
- 停牌/ST/涨跌停优先使用已同步的 `trading_status`；没有同步时按日线和交易日历
  现场推导，ST 判断依赖能拿到的股票名称。

信号映射规则：

| 上游文本 | 动作 |
|---|---|
| 含「买入 / 加仓 / 增持 / 建仓 / buy / add / accumulate」且未被否定 | 买 |
| 含「卖出 / 减仓 / 清仓 / 减持 / sell / reduce / avoid」且未被否定 | 卖 |
| 前面 3 个字含「不 / 别 / 勿 / 谨慎 / 暂不 / 不宜」 | 视为否定，忽略 |
| `decision_signals.action` 为 `buy/add` | 买 |
| `decision_signals.action` 为 `sell/reduce/avoid` | 卖 |

同一 `(日期, 代码, 动作)` 会去重。

#### 保存与查看

- 勾选「保存到个人库」后才会出现在「总览 → 最近回测」。
- 保存内容包括运行配置、指标 JSON、逐笔交易。
- 不勾选只返回结果，不落库。

### 4.4 插件

页面展示：

- 已加载插件：名称、版本、类型、显示名、描述、权限。
- 插件加载错误：单个插件失败不影响其他插件。

插件目录默认 `plugins/<name>/`，发现规则是 `plugins/*/plugin.yaml`。
新增/调试插件见 §8。

### 4.5 QMT

- 只读健康检查：调用 Windows QMT 桥的 `GET /health`，不会下单。
- 页面显示桥地址和 `只读/未启用` / `交易已启用`。
- 桥不可达时显示错误文本，不影响其他功能。
- 实盘执行不在本页面；默认 `QMT_TRADING_ENABLED=false`、`QMT_REQUIRE_CONFIRM=true`。

---

### 4.6 深度复盘

`/personal` → **深度复盘** tab，11 张卡片（机构式多指标印证；卡片注册表
`REVIEW_CARDS` 里加一项即新增指标）：

| 卡片 | 内容 | 性质 | 数据更新 |
|---|---|---|---|
| 市场综合状态 | 各指标一年滚动分位加权 → 0-100 综合分 + 状态灯（冰点/偏冷/中性/偏热/过热），分量表带顺势/逆向标签 | 综合 | 随各指标自动计算 |
| 市场宽度（TRIN） | 当日 TRIN/分位带、涨跌家数、上证指数、判读与背离、30 日曲线 | 量能 | CLI `import-arms`（§7.5） |
| 期指做空压力 | IF/IH/IC/IM 基差/基差率/持仓量、30 日基差率曲线 | 定价 | 定时同步 / 「更新」按钮 |
| 期指会员持仓 | 前 20 会员持买单量/持卖单量/**净空占比**（中金所官方 CSV） | 定价（逆向） | 同上 |
| 融资余额 | 两融总计 + 5 日变化、沪/深、四板块余额 | 杠杆 | 同上 |
| 涨停梯队 | 涨停/首板/最高连板、**炸板率**、**昨涨停今收益**（亏钱效应） | 结构 | 同上 |
| 期权 PCR | 50ETF 认沽/认购成交量 PCR + 持仓量 PCR（上交所官方统计） | 定价（逆向） | 同上（无第三方限频） |
| 资金面 | **两融交易占比**（>10% 过热 / <7% 冰点）、7 只宽基 ETF 份额及日变化、全市场成交额 | 资金 | 同上 |
| 行业拥挤度 | 成交占比最高的 15 个行业 + 各自 250 日分位（>90% 拥挤警戒） | 结构 | 同上（快照自建积累） |
| 宏观锚 | 中美 10Y/2Y 利差曲线 + 未来 60 天解禁日历 | 宏观 | 同上（利差含全量历史） |
| 更多指标（规划中） | 北向活跃度、新基金发行、龙虎榜席位 | — | — |

**使用纪律（机构做法）**：所有指标看分位而非绝对值；逆向指标（PCR/净空占比/
炸板率）与顺势指标（两融占比/连板高度/上涨占比）分开解读——同为高分位，
前者常是阶段底信号，后者是过热信号；综合分只是平均而非买卖信号。

说明：

- 基差 = 期货收盘 − 现货收盘，**贴水（负）= 对冲/做空压力大**；基差率 = 基差/现货。
- 融资余额板块行只统计**股票标的**，与沪/深市汇总的差值≈ETF/债券/可转债口径。
- 两融数据 **T+1 发布**（11-17 的数据 11-18 早上才有）；板块拆分按交易所每日明细聚合，一次同步最多 120 天。

### 4.7 定时同步（RM-05）

Docker Compose 提供 **personal-sync** 副服务（与 server 共享 `data/personal.db`），
每天 **06:00**（容器时区 Asia/Shanghai）自动增量同步 14 个数据集：

| 顺序 | 数据集 | 回看窗口 | 说明 |
|---|---|---|---|
| 1 | 交易日历 calendar | 前 30 天 ~ 后 60 天 | 状态同步依赖它 |
| 2 | 交易状态 status | 前 15 天 | 停牌/ST/涨跌停 |
| 3 | 日线 bars | 前 15 天 | 增量幂等 upsert |
| 4 | 复权因子 adjust | 前 30 天 | Tushare 免费档 1 次/小时 |
| 5 | 期指 futures | 前 10 天 | IF/IH/IC/IM + 基差 |
| 6 | 成交概况 turnover | 前 30 天 | 两融交易占比的分母 |
| 7 | 两融 margin | 前 10 天 | T+1 发布，见 §7.6 |
| 8 | 期指持仓 cffex_rank | 前 10 天 | 中金所前 20 会员 |
| 9 | 涨停梯队 zt | 前 10 天 | 东财涨停池/炸板/昨涨停 |
| 10 | 期权 PCR pcr | 前 10 天 | 上交所官方统计，无第三方限频 |
| 11 | 行业拥挤 sector | 当日快照 | 同花顺行业成交额 |
| 12 | ETF 份额 etf_share | 当日快照 | 份额序列自建积累 |
| 13 | 中美利差 bond | 全量历史 | 东财债券收益率 |
| 14 | 解禁 release | 后 45 天 | 东财解禁汇总 |

- 每个数据集的结果写入**数据新鲜度**表（总览可见最近成功时间/数据日期/错误）；
  单个数据集失败不影响其余数据集，第二天自动重试。
- 阿姆氏快照默认不在 NAS 上自动更新（easy-daily-trading 在本地 Mac）。
  如需自动导入，把快照目录挂载进容器并追加 `--arms-dir`（见 docker-compose.yml 注释）。
- 手动立即跑一轮：`docker compose exec personal-sync python -m personal.cli.main schedule --once`
- 调整时间：修改 compose 中 `--at 06:00`（如 `--at 05:00`），`docker compose up -d personal-sync` 生效。

## 5. CLI 参考

通用形式：

```bash
python -m personal.cli.main <command> [options]
```

| 命令 | 作用 | 关键参数 |
|---|---|---|
| `init-db` | 创建/初始化个人库 | — |
| `info` | 显示配置、上游契约、插件状态 | — |
| `demo` | 合成数据组合回测 | `--days N`（默认 500）、`--save` |
| `sync` | 同步全部个人数据集 | `--dataset bars\|adjust\|calendar\|status\|futures\|margin\|turnover\|zt\|pcr\|cffex_rank\|sector\|etf_share\|bond\|release`、`--source`、`--code`（可重复）、`--start`、`--end`、`--cross-check` / `--no-cross-check` |
| `replay` | 回放上游建议 | `--start`、`--end`、`--include both\|analyses\|signals`、`--save` |
| `import-arms` | 导入阿姆氏（TRIN）日快照 | `--dir`（easy-daily-trading 的 `cache/arms_index/daily`） |
| `breadth` | 查看已导入的市场宽度 | `--days N`（默认 5） |
| `schedule` | 定时增量同步（默认 06:00 每日循环） | `--at HH:MM`、`--datasets`、`--arms-dir`、`--once`（立即跑一轮并退出） |
| `plugins` | 列出插件和加载错误 | — |
| `web` | 启动独立控制台 | `--host`、`--port`、`--reload` |

示例：

```bash
# 初始化
python -m personal.cli.main init-db

# 看状态
python -m personal.cli.main info

# 离线演练
python -m personal.cli.main demo --days 400 --save

# 同步一只股票最近两年
python -m personal.cli.main sync --source auto --code 600519 \
  --start 2024-01-01 --end 2026-11-16

# 同步多只 + 复权因子
python -m personal.cli.main sync --source tushare \
  --code 600519 --code 000001 --start 2024-01-01
python -m personal.cli.main sync --dataset adjust --source tushare \
  --code 600519 --start 2024-01-01

# 交易日历 + 交易状态（状态会用到日历和日线）
python -m personal.cli.main sync --dataset calendar --source baostock \
  --start 2024-01-01 --end 2026-11-16
python -m personal.cli.main sync --dataset status --code 600519 \
  --start 2024-01-01 --end 2026-11-16

# 回放上游建议
python -m personal.cli.main replay --start 2025-01-01 --end 2026-11-16 \
  --include both --save

# 插件
python -m personal.cli.main plugins

# 导入阿姆氏快照并查看最近 5 天
python -m personal.cli.main import-arms \
  --dir /Users/mao/vibecoding/easy-daily-trading/cache/arms_index/daily
python -m personal.cli.main breadth --days 5

# 股指期货主力合约（IF/IH/IC/IM + 基差）与融资余额（分板块）
python -m personal.cli.main sync --dataset futures --start 2026-11-10 --end 2026-11-17
python -m personal.cli.main sync --dataset margin --start 2026-11-10 --end 2026-11-17

# 立即跑一轮完整定时同步（验证用）
python -m personal.cli.main schedule --once --at 06:00
```

日期参数省略时：`sync` 默认最近 730 天；`replay` 默认最近 365 天。

---

## 6. 回测规则与指标口径

### 6.1 成交规则

| 规则 | 实现 |
|---|---|
| 信号时点 | 收盘后产生信号（日 D） |
| 成交时点 | **下一交易日开盘** |
| 整手 | 100 股整数倍 |
| T+1 | 当日买入的股份当日不可卖 |
| 停牌 | 跳过，不成交 |
| 涨跌停 | 开盘价触及涨停不买、触及跌停不卖；收盘涨跌停标记只用于展示，避免未来函数 |
| ST | 默认排除 |
| 仓位 | 最多 10 个持仓，单票上限 10% |
| 初始资金 | 默认 1,000,000 |
| 基准 | 默认 `000300.SH` |

### 6.2 费用

| 项目 | 默认值 | 方向 |
|---|---|---|
| 佣金 | 2.5bp，最低 5 元 | 买、卖 |
| 印花税 | 5bp（0.05%） | 仅卖出、非 ETF |
| 过户费 | 0.1bp | 买、卖 |
| 滑点 | 5bp | 买加价、卖减价 |
| 红利税 | 持有 ≤30 天 20%；31–365 天 10%；>365 天 0% | 分红时 |

> ETF 免印花税；费用参数在 `personal/backtest/costs.py` 的 `CostConfig` 中集中定义。

### 6.3 指标

| 指标 | 口径 |
|---|---|
| 累计收益 | 期末净值 / 期初净值 − 1 |
| 年化收益 CAGR | 按自然日折算（365.25 天/年） |
| 年化波动 | 日收益标准差 × √244 |
| Sharpe | 日收益均值 × 244 / 年化波动（无风险利率默认 0） |
| 最大回撤 | `min(净值 / 历史最高净值 − 1)` |
| Calmar | 年化收益 / \|最大回撤\| |
| 基准收益 | 基准期末 / 期初 − 1 |
| 超额收益 | 策略累计收益 − 基准收益 |
| 胜率 | 盈利平仓笔数 / 平仓笔数 |
| 盈亏比 | 盈利总额 / \|亏损总额\| |
| 换手率 | 总成交额 / 平均净值 |
| 总费用 | 所有交易费用之和 |
| 交易数 / 平仓数 | 成交笔数 / 卖出笔数 |

> 样本太短或没有平仓时，部分指标为空（页面显示 `-`），这是正常的。

### 6.4 局限性

- 日线级别、下一日开盘成交，不模拟盘中滑点和排队。
- 不模拟分红送转的现金流（复权用于价格连续性；红利税函数已提供但未接入事件）。
- 不模拟融资融券、期权、ETF 申赎。
- 停牌/ST/涨跌停来自 `trading_status`（可用「交易状态」同步）。没有同步时，
  回测会按日线 + 交易日历现场推导；但 **ST 判断依赖股票名称**，名称拿不到时按
  非 ST 处理，涨跌停幅度可能偏宽。
- 停牌只在「首个日线到最后一个日线」之间识别；末尾的停牌和“还没下载”无法区分，
  不会生成状态行。
- 每个代码的首个交易日没有前收盘，无法判断涨跌停。
- 涨跌停幅度按板块规则估算（主板 10%、创业板/科创板 20%、北交所 30%、主板 ST 5%），
  不处理交易所临时调整的特殊情形。
- 合成 Demo 数据是随机生成的，只能验证流程，不能用于策略判断。

---

## 7. 数据与口径

### 7.1 个人库表

| 表 | 主键 | 内容 |
|---|---|---|
| `daily_bar` | `(code, trade_date, source)` | 原始日线（未复权） |
| `adjust_factor` | `(code, ex_date, source)` | 累计复权因子 |
| `trading_calendar` | `trade_date` | 交易日（开市日） |
| `trading_status` | `(code, trade_date)` | 停牌/ST/涨跌停标记 |
| `fund_nav` | `(code, nav_date, source)` | 基金净值（Phase 2） |
| `etf_snapshot` | `(code, trade_date, source)` | ETF 快照（Phase 2） |
| `market_breadth` | `trade_date` | 市场宽度/阿姆氏 TRIN 日汇总（见 §7.5） |
| `index_futures` | `(trade_date, symbol)` | IF/IH/IC/IM 主力合约价、持仓、基差 |
| `margin_balance` | `(trade_date, scope_type, scope)` | 两融余额（market=沪/深/总计；board=四板块，仅股票） |
| `market_turnover` | `trade_date` | 沪/深股票成交额（两融占比分母） |
| `limit_up_stats` | `trade_date` | 涨停/首板/连板高度/炸板率/昨涨停今收益 |
| `option_pcr` | `(trade_date, underlying)` | ETF 期权 PCR（50ETF/300ETF，成交量口径） |
| `futures_rank` | `(trade_date, symbol)` | 中金所前 20 会员多空持仓汇总 |
| `sector_amount` | `(trade_date, board)` | 同花顺行业成交额与占比（拥挤度） |
| `etf_share` | `(trade_date, code)` | 宽基 ETF 份额快照（自建积累） |
| `bond_yield` | `trade_date` | 中美国债 2Y/10Y 收益率与利差 |
| `restricted_summary` | `release_date` | 解禁日历（家数/数量/实际解禁市值） |
| `data_quality_event` | 自增 | 质检事件 |
| `backtest_run` | `run_id` | 回测配置 + 指标 |
| `backtest_trade` | 自增 | 回测逐笔交易 |
| `trade_journal` | 自增 | 交易日志（Phase 2） |

### 7.2 复权

- 因子是**累计份额乘数**（Tushare `adj_factor` 口径）。
- 前复权：`raw × factor(date) / factor(latest)`
- 后复权：`raw × factor(date) / factor(first)`
- 个人库存**原始价**，复权在读取/分析时计算，避免重复入库。
- 回测默认按**后复权**处理，涨跌停价会同步换算到复权后的价格空间。

### 7.3 数据质量规则

| 规则 | 含义 |
|---|---|
| `duplicate_date` | 同代码同日期重复 |
| `non_positive_price` | 价格 ≤ 0 |
| `ohlc_inconsistent` | 最高/最低/开收关系不成立 |
| `negative_volume_or_amount` | 成交量/成交额为负 |
| `extreme_jump` | 单日涨跌幅异常 |
| `close_price_mismatch` | 跨源收盘价差异 |
| `volume_mismatch` | 跨源成交量差异 |
| `missing_trading_day` | 缺失交易日 |

单源检查在每次日线同步时自动执行；`close_price_mismatch` / `volume_mismatch` 只有在
开启「跨源校验」且存在第二个可用数据源时才会产生；`missing_trading_day` 需要先有
交易日历。

### 7.4 源隔离

同一代码可能从多个源同步过。`get_bars()` 只选**一个**源：

1. 在 `PERSONAL_DATA_SOURCE_PRIORITY` 列出的源里，选请求区间内**行数最多**的
   （行数相同时按优先级）；
2. 没有命中优先级列表时，选全局行数最多的源。

这样既避免混源失真，也避免「优先源只补了几天的数据，把完整的历史序列盖掉」。

> 如果确实要让某个短区间的新源覆盖旧源，先把该区间之外的数据也同步完整，
> 或调整优先级/删除旧源数据。

---

### 7.5 市场宽度与阿姆氏指标（TRIN）

市场宽度表 `market_breadth` 存每个交易日的全市场汇总，供「深度复盘」（建设中）
和 API `/api/market/breadth?days=N` 使用。

**数据来源**：另一个本地项目 `easy-daily-trading`（`tools/arms_index.py`，腾讯/新浪
前复权日线，剔除北交所与 ST）。在那边每天跑一次：

```bash
cd /Users/mao/vibecoding/easy-daily-trading
python3 tools/arms_index.py --days 3          # 更新 cache/arms_index/daily/
```

然后回这边导入（可重复执行，按日期幂等覆盖）：

```bash
python -m personal.cli.main import-arms \
  --dir /Users/mao/vibecoding/easy-daily-trading/cache/arms_index/daily
python -m personal.cli.main breadth --days 5
```

**口径**（移植自 easy-daily-trading，A 股 250 日实测分位，不套美股 1.0 中枢）：

- `TRIN = (上涨家数 ÷ 下跌家数) ÷ (上涨成交量 ÷ 下跌成交量)`；另存按成交额口径的 `TRIN(额)` 交叉校验
- 分位带：`<0.405 极低`、`0.579 偏低`、`0.780 中低位`、`1.122 中高位`、`1.428 偏高`、`1.747 高位`、`>1.747 极高`
- 判读必须结合**上涨占比**：同样 TRIN 0.40，普涨日=量能集中在龙头（健康）；普跌日=资金抱团避险（恐慌但常近短期底）
- 指数背离（对照上证指数 20 日窗口）：`顶部信号` = 指数新高但量能跟不上，警惕回落；`底部信号` = 指数新低且抛压集中，常近短期底。**背离是风险提示，不是买卖信号**
- 成交量单位为亿股、成交额为亿元（表列名带 `_yi` 后缀即为此含义）

**已导入数据**：2025-10-16 ~ 2026-11-17 共 265 个交易日（来源标记 `easy_daily_trading`）。

### 7.6 股指期货与融资余额口径

**股指期货**（`index_futures` 表，来源 AkShare `futures_main_sina` + 新浪现货指数）：

- 主力连续合约 IF0（沪深300）/ IH0（上证50）/ IC0（中证500）/ IM0（中证1000）
- `basis = 期货收盘 − 现货收盘`；`basis_pct = basis / 现货 × 100`
- 贴水（负）= 对冲/做空压力大；主力换月时主力连续价格有跳空，跨月比较需注意

**融资余额**（`margin_balance` 表，来源上交所/深交所官方数据）：

- `market` 行：沪市/深市/总计，官方汇总口径（含基金/债券标的）；深市官方单位为亿元，入库统一为元
- `board` 行：沪主板/科创板/深主板/创业板，由每日**个股明细**按代码前缀聚合（60x/688-689/000-003/300-302），**仅股票**
- 板块之和 < 汇总之差 = ETF/债券/可转债等非股票标的
- T+1 发布；明细按日逐日拉取，单次同步区间 ≤ 120 天（`MARGIN_MAX_DAYS`）
- 上交所明细单页 2000 行，同步时自动翻页收齐

### 7.7 深度市场指标口径（P1/P2 卡片）

| 指标 | 来源 | 口径与用法 |
|---|---|---|
| 两融交易占比 | `margin_balance.rzye_buy ÷ market_turnover.total` | 情绪杠杆温度计：>10% 过热 / <7% 冰点（顺势） |
| 涨停梯队/炸板率/昨涨停今收益 | 东财涨停池（盘后终值） | 炸板率=炸板/(涨停+炸板)，>40% 亏钱效应；昨涨停今收益深负=退潮（结构） |
| 期权 PCR | 上交所官方「期权统计」（AkShare `option_daily_stats_sse`，按日一接口） | 成交量与持仓量 PCR 均为**交易所聚合完整口径**；官方百分数入库除以 100；50ETF/300ETF（逆向） |
| 期指会员持仓 | 中金所官方 CSV（GBK，产品内全部上市合约累加前 20 会员） | 净空占比=(持卖−持买)/(持买+持卖)（逆向） |
| 行业拥挤度 | 同花顺行业一览 `总成交额`（90 个行业） | 占比=板块成交额/合计；250 日分位>90%=拥挤警戒（快照自建，从启用日积累） |
| ETF 份额 | 东财 ETF 快照（7 只宽基固定名单） | 份额无历史 API，每日快照自建序列；份额骤增=宽基托底资金 |
| 中美利差 | 东财 `bond_zh_us_yield_em`（全量历史） | 10Y/2Y 利差走阔压制风险偏好（月/周级别） |
| 解禁日历 | 东财解禁汇总 | 未来 45 天逐日家数/实际解禁市值 |
| 综合状态 | 上述指标 + TRIN 上涨占比 | 一年滚动分位（样本<20 跳过）平均；0-25 冰点 / 25-40 偏冷 / 40-60 中性 / 60-75 偏热 / 75-100 过热 |

## 8. 插件使用与开发

### 8.1 目录结构

```text
plugins/
└── obv/
    ├── plugin.yaml
    └── plugin.py
```

### 8.2 Manifest

```yaml
api_version: "1.0"
name: obv
version: "0.1.0"
type: indicator
display_name: OBV 能量潮
description: 计算 OBV、OBV 均线与价格/能量背离
entry: plugin:OBVIndicator
requires:
  personal: ">=0.1.0"
permissions:
  - market_data:read
config_schema:
  window:
    type: integer
    default: 20
    minimum: 2
    maximum: 250
```

字段规则：

- `api_version` 必须是 `1.0`。
- `type` 可选：`indicator`、`fund_metric`、`report_section`、`data_source`、
  `strategy`、`execution_adapter`、`journal_hook`。
- `entry` 必须是 `模块:类名`，模块文件在插件目录下。
- `permissions` 仅作声明，当前不强制。

### 8.3 指标插件协议

```python
import pandas as pd
from typing import Any, Mapping


class OBVIndicator:
    name = "obv"
    version = "0.1.0"
    required_columns = ("close", "volume")

    def compute(self, df: pd.DataFrame, params: Mapping[str, Any]) -> pd.DataFrame:
        ...

    def summarize(self, df: pd.DataFrame, params: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def render(self, summary: dict[str, Any], *, language: str = "zh") -> str:
        ...
```

- 只允许 `import personal.plugins.api`（以及 pandas/numpy 等第三方库）。
- **禁止**导入上游 `src.*` 或个人层业务模块（如 `personal.backtest.engine`）。
- 指标插件必须提供 `name/version/compute/summarize/render`；策略插件必须提供
  `name/generate_targets`。
- 单个插件失败只记录错误，不影响其他插件。

### 8.4 加载与调试

```bash
python -m personal.cli.main plugins
```

- 默认扫描 `PERSONAL_PLUGIN_DIRS` 下每个子目录的 `plugin.yaml`。
- 设 `PERSONAL_PLUGIN_ALLOWLIST=obv,my_indicator` 可只加载白名单。
- Docker 中默认镜像内置 `plugins/`；想热更新可取消 Compose 里
  `../plugins:/app/plugins:ro` 的注释并重启容器。

---

## 9. QMT 桥

### 9.1 定位

- 桥运行在**Windows QMT 机器**上，通过 HTTP 暴露行情/持仓/订单接口。
- NAS/macOS 上的个人层只做健康检查；默认不交易。
- 中信建投 QMT 是否开放 miniQMT/xtquant，需要在本机确认；桥支持 `mock` 与
  `xtquant` 两种适配器。

### 9.2 启动（Windows）

```bash
cd qmt-bridge
pip install -r requirements.txt
set QMT_BRIDGE_TOKEN=change-me
python app.py
```

默认监听 `8710`。

### 9.3 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/health` | 桥与 QMT 连接状态 |
| GET | `/quote?codes=600519.SH` | 行情 |
| GET | `/positions` | 持仓 |
| GET | `/orders` | 委托 |
| GET | `/trades` | 成交 |
| POST | `/orders` | 下单（需显式开启） |
| POST | `/orders/{id}/cancel` | 撤单 |
| POST | `/reconcile` | 对账 |

### 9.4 安全默认

- `QMT_TRADING_ENABLED=false`：下单接口拒绝执行。
- `QMT_REQUIRE_CONFIRM=true`：下单需要二次确认。
- 不要把桥暴露到公网；用局域网 + token。
- 启用实盘前必须先在模拟盘跑通，并显式修改配置。

---

## 10. 数据备份、升级与排障

### 10.1 需要备份的文件

| 路径 | 内容 |
|---|---|
| `data/personal.db`（+ `-wal`/`-shm`） | 个人库：行情、回测、日志 |
| `data/stock_analysis.db` | 上游库：分析历史、持仓、决策信号 |
| `config/personal.env`、`.env` | 配置与 token |
| `plugins/` | 自定义插件 |
| `strategies/` | 策略 YAML |

SQLite 备份建议先停容器/进程，或用 `sqlite3 personal.db ".backup backup.db"`，
不要在写入过程中直接复制 WAL 文件。

### 10.2 升级

```bash
git pull
# 上游改了 UI 集成文件时：
git apply --check patches/0001-personal-web-integration.patch
git apply patches/0001-personal-web-integration.patch
cd apps/dsa-web && npm run build && cd ../..

# Docker
docker compose -f docker/docker-compose.yml build server
docker compose -f docker/docker-compose.yml up -d server
```

升级前备份 `data/` 和 `config/`。

### 10.3 故障排查

| 现象 | 检查 |
|---|---|
| `/personal` 404 | 镜像/启动是否包含最新前端；`PERSONAL_API_ENABLED=true` |
| 页面空白 | 浏览器控制台；确认 `static/assets/PersonalPage-*.js` 存在；重新构建前端 |
| `上游 DSA 未生成` | 正常，先跑一次上游分析 |
| Replay 报 `no local bars` | 先同步信号涉及的代码 |
| 同步全部失败 | 看 `errors`；Tushare 权限/限流、BaoStock 网络、代码是否北交所 |
| 数据覆盖为空 | 同步是否成功；`PERSONAL_DB` 是否指向同一个库 |
| 交易日历同步失败 | 换 `baostock`/`akshare`；都失败时会从已有日线派生（source=`derived`） |
| 交易状态 rows 为 0 | 先同步日线；状态需要本地日线才能推导 |
| 停牌/涨跌停不生效 | 是否先同步了交易日历和交易状态；无日线的日期会被视为停牌 |
| 复权后价格和行情软件不同 | 回测默认后复权（hfq），与软件前复权显示不同属正常 |
| 跨源校验很慢 | 取消勾选或设 `PERSONAL_CROSS_SOURCE_CHECK=false` |
| 插件不显示 | `plugin.yaml` 是否在 `plugins/<name>/`；`plugins` 命令看错误 |
| 数据库无法写入 | `data/` 权限；不要用 SMB/NFS；Docker entrypoint 会尝试 chown |
| 8000 端口冲突 | `API_PORT=8010` 覆盖 |
| QMT 未连接 | 桥是否在 Windows 启动；`QMT_BRIDGE_URL` 是否可达；token 是否一致 |
| ARM64 构建慢/失败 | 在目标机构建；确认基础镜像支持 arm64 |

---

## 11. 术语表

| 术语 | 解释 |
|---|---|
| 复权因子 | 把历史价格换算到可比口径的累计乘数 |
| 前复权 / 后复权 | 以最新/最早价格为基准调整历史价格 |
| T+1 | 当日买入的股票下一交易日才能卖 |
| 整手 | A 股买入数量为 100 股的整数倍 |
| 滑点 | 理论价格与成交价格的差，回测中用 bps 模拟 |
| 印花税 | 卖出时按成交额收取，ETF 免征 |
| 换手率 | 成交额 / 平均净值，衡量交易频繁程度 |
| 最大回撤 | 从历史高点到低点的最大跌幅 |
| Sharpe | 单位波动获得的超额收益 |
| Calmar | 年化收益 / 最大回撤 |
| Replay | 把上游 AI 建议当信号，用历史行情重放 |
| 源隔离 | 同一代码只使用一个数据源，避免混源 |
| bps | 万分之一 |

---

## 12. 文档维护约定（新增功能必读）

**规则：每个新增或改变用户可见行为的功能，必须在同一个提交里更新本手册。**

用户可见行为包括：页面标签/字段/按钮、CLI 命令/参数、环境变量、API 路径、
数据源、回测规则、指标口径、插件协议、QMT 接口。

提交前检查：

- [ ] 本手册对应章节已更新（新功能加新章节，并在 §0 导航表加一行）。
- [ ] `docs/CHANGELOG_PERSONAL.md` 新增 `CHG-XXXX`，`Files` 表包含本手册。
- [ ] 如果是路线图事项，更新 `docs/ROADMAP_PERSONAL.md` 的状态。
- [ ] `docs/AI_CONTEXT.md` 的入口/命令/API/限制有变化时同步更新。
- [ ] 命令和字段名与实际代码一致（能从代码里直接搜到）。
- [ ] 没有写入 token、密码、账号等敏感信息。
- [ ] 如果改了架构或边界，更新
      `docs/PERSONAL_EXTENSION_ARCHITECTURE.md`。

新功能手册小节模板：

```markdown
### 4.x 功能名

**用途：** 一句话说明解决什么问题。

**入口：** 页面标签 / CLI 命令 / API。

**操作步骤：**
1. ...
2. ...

**字段说明：**

| 字段 | 含义 |
|---|---|
| ... | ... |

**限制与注意事项：**
- ...

**相关配置：** `ENV_NAME`（默认值）
```

> 面向 AI/agent 的索引在 `docs/AI_CONTEXT.md`；本手册面向人，尽量用「点哪里、
> 填什么、看到什么」的描述，不堆实现细节。
