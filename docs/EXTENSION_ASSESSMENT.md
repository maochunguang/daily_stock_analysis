# daily_stock_analysis 扩展能力评估与建议

> 评估对象：`ZhuLinsen/daily_stock_analysis`（`main` 分支）
> 评估日期：2026-11-12
> 评估范围：插件机制、自定义指标、自定义 Prompt、报告模板、数据源、通知、Agent 工具、选股与告警

---

## 一、结论摘要

该项目采用 **“配置驱动 + 代码内注册表”** 的扩展模型，**没有正式的插件系统**（无 `entry_points`、无 `pluggy`、无动态插件发现/生命周期）。它提供了多个可用的扩展点，但不同能力的开放程度差异很大：

| 能力 | 现状 | 能否零代码扩展 |
|---|---|---|
| 插件机制 | 无正式插件系统；扩展点分散在代码注册表中 | ❌ |
| 分析策略（Skill） | 强：YAML 自然语言策略，支持自定义目录、同名覆盖内置 | ✅ 完全支持 |
| 选股策略 | 强：YAML 定义硬过滤、因子权重、评分参数 | ✅ 调参可零代码；新增因子需改代码 |
| 自定义指标（主分析） | 弱：主 Prompt 只注入 MA5/10/20、量比；MACD/RSI 有计算但不进主 Prompt | ⚠️ 需改 3~4 处代码 |
| 自定义指标（告警） | 中等：MA/RSI/MACD/KDJ/CCI 五类，参数可配 | ⚠️ 新增类型需改代码 |
| 自定义 Prompt | 部分：只能通过策略 YAML 的 `instructions` 注入系统提示词 | ⚠️ 不能整体替换/追加任意 Prompt |
| 报告模板 | 强：Jinja2 模板 + `REPORT_TEMPLATES_DIR` | ✅ 完全支持 |
| 通知渠道 | 14+ 内置渠道 + 自定义 Webhook Body 模板 | ✅ 自定义服务可用 Webhook 兜底；新增原生渠道需改代码 |
| 行情数据源 | `BaseFetcher` 抽象清晰，但注册硬编码 | ⚠️ 新增数据源需改 `_init_default_fetchers` |
| Agent 工具 | `ToolRegistry` + `@tool` 装饰器，启动时靠 import 注册 | ⚠️ 新增工具需改代码 |

**一句话总结**：换策略、换报告格式、换通知服务基本可以零代码完成；新增技术指标、整体自定义 Prompt 必须修改核心代码。当前最值得补齐的是 **指标插件** 与 **可组合 Prompt** 两层能力。

---

## 二、架构速览

```text
main.py / StockAnalysisPipeline
  ├─ DataFetcherManager (data_provider/base.py)
  │    └─ BaseFetcher: _fetch_raw_data / _normalize_data / _calculate_indicators
  ├─ StockTrendAnalyzer (src/stock_analyzer.py)     # MA/MACD/RSI/量能/支撑压力
  ├─ News / Search / Fundamental / Chip / MarketContext
  ├─ AnalysisContextPack → Prompt 摘要
  ├─ GeminiAnalyzer (src/analyzer.py)
  │    ├─ SYSTEM_PROMPT（硬编码模板）
  │    ├─ SkillManager → strategies/*.yaml → 注入“激活的交易技能”
  │    └─ _format_prompt（硬编码用户 Prompt 拼装）
  └─ Report / Notification / History / Alerts / Screening
```

---

## 三、扩展点逐项结论

### 3.1 策略（Skill）扩展：最成熟

- 内置策略目录：`strategies/*.yaml`（15 个），启动时自动加载。
- 自定义目录：`AGENT_SKILL_DIR=./my_skills`，同名覆盖内置（见 `strategies/README.md`、`src/agent/factory.py:454-488`）。
- Schema 支持：`name / display_name / description / category / core_rules / required_tools / aliases / default_active / default_router / default_priority / market_regimes / instructions`。
- 注入方式：`_get_analysis_system_prompt()` 把激活策略的 `instructions` 拼进系统提示词的 `## 激活的交易技能` 段（`src/analyzer.py:2683-2745`）。
- 限制：纯自然语言，不能写计算逻辑；不能新增结构化字段；不能修改用户 Prompt 的数据段；无版本与沙箱。

### 3.2 自定义指标：部分支持，主分析链路缺口明显

**数据层**：`BaseFetcher._calculate_indicators()` 只计算 `ma5/ma10/ma20/volume_ratio`（`data_provider/base.py:577-604`）。

**趋势分析层**：`StockTrendAnalyzer` 额外计算 MACD、RSI(6/12/24)、MA60、支撑压力、乖离率（`src/stock_analyzer.py:206-340`）。

**但主分析 Prompt 只拿到一部分**：`pipeline._enhance_context()` 写入的 `enhanced['trend_analysis']` 只有趋势状态、均线排列、趋势强度、乖离、量能、信号分（`src/core/pipeline.py:1084-1097`），**MACD/RSI 数值没有进入主 Prompt**。它们只在 Agent 工具 `analyze_trend` 的返回里可见（`src/agent/tools/analysis_tools.py`）。

**告警层**：`TECHNICAL_ALERT_TYPES = {ma_price_cross, rsi_threshold, macd_cross, kdj_cross, cci_threshold}`，参数归一化、K 线需求、评估函数均为 if/else 硬编码（`src/services/alert_indicators.py:14-107`）。新增指标需改 5 处：类型集合、参数归一化、所需 K 线数、评估分支、`alert_service` 校验。

**选股层**：因子库固定 9 个（`momentum / value / liquidity / reversal / activity / stability / size / theme_heat / topic_alignment`，`src/services/screening/scorer.py:7-19`），硬过滤字段固定（`src/services/screening/models.py:12-50`）。YAML 可以调权重和阈值，但**不能新增因子**。

### 3.3 自定义 Prompt：只有“策略片段”一个口子

- 系统提示词是硬编码模板：`GeminiAnalyzer.SYSTEM_PROMPT`（`src/analyzer.py:2150`）。
- 用户提示词是硬编码拼装：`_format_prompt()`（`src/analyzer.py:4353-5135`），按行情/均线/实时/筹码/资金流/新闻等区块逐段 `prompt +=`。
- 没有 `CUSTOM_PROMPT`、`PROMPT_SUFFIX`、`SYSTEM_PROMPT_OVERRIDE` 之类的配置；`config_registry.py` 中与 Prompt 相关的只有缓存遥测开关。
- API `AnalyzeRequest` 只有 `skills` 字段，没有 prompt 参数（`api/v1/schemas/analysis.py:34-92`）。
- 唯一自定义入口：策略 YAML 的 `instructions`，且只能进入系统提示词的技能段。
- 报告格式可以改：`REPORT_RENDERER_ENABLED + REPORT_TEMPLATES_DIR`，模板位于 `templates/report_markdown.j2` 等；但模板数据源是固定的 `AnalysisResult` 字段（`REPORT_TEMPLATES_DIR` 定义见 `src/core/config_registry.py:2703`）。

### 3.4 其他扩展点

| 扩展点 | 位置 | 机制 | 是否需改代码 |
|---|---|---|---|
| 选股策略 | `src/services/screening/strategies/*.yaml`、`STRATEGIES_DIR` | YAML → `load_strategy()` | 调参不需要；新因子需要 |
| 报告模板 | `templates/*.j2`、`REPORT_TEMPLATES_DIR` | Jinja2 | 不需要 |
| 通知 | `src/notification.py` + `notification_sender/*` | 枚举 + 硬编码检测（`src/notification.py:185,495-566`） | 自定义服务用 Webhook 可零代码；原生渠道需改代码 |
| 数据源 | `BaseFetcher` / `DataFetcherManager(fetchers=...)` | 抽象类 + 列表注入 | 需在 `_init_default_fetchers()`（`data_provider/base.py:1794`）注册 |
| Agent 工具 | `ToolRegistry.register()` / `@tool`（`src/agent/tools/registry.py:337`） | 代码注册 | 需 import 注册 |
| LLM 供应商 | LiteLLM | 配置驱动 | 不需要（兼容 OpenAI 协议即可） |
| Web 配置页 | `src/core/config_registry.py` | 字段注册表 | 新增配置项需改代码 |

---

## 四、差距分析：为什么现在还不是“插件系统”

1. **没有发现机制**：无 `entry_points`、无 `plugins/` 目录扫描、无 manifest。
2. **没有生命周期**：无 load/init/health/unload，单个插件失败可能升级为进程级异常。
3. **没有稳定契约**：数据源、指标、通知、工具各自为政，没有统一的 `PluginContext` 与 API 版本。
4. **Prompt 是模板硬编码**：没有可组合的 section 机制，无法在不改 `analyzer.py` 的情况下插入新段落。
5. **结构化输出固定**：`AnalysisResult` 字段固定，新增指标无法进入报告 JSON、前端与回测。

---

## 五、三条建议

### 建议一（短期，零代码）：先用满现有扩展点

**目标**：在不改核心代码的前提下，满足策略定制、报告格式定制、通知渠道定制。

**做法**：

1. **分析策略/视角定制**：在 `strategies/` 或 `AGENT_SKILL_DIR` 下新增 YAML，用自然语言写判断标准、入场/出场条件、评分调整，可引用 `get_daily_history`、`analyze_trend` 等工具。
   ```env
   AGENT_SKILL_DIR=./my_skills
   AGENT_SKILLS=my_strategy
   ```
2. **选股策略定制**：在 `STRATEGIES_DIR` 下新增 YAML，调整 `hard_filters`、`factor_weights`、`scoring_profile`、`risk_profile`、`portfolio_profile`，无需改代码。
3. **报告格式定制**：复制 `templates/report_markdown.j2` 等模板到自定义目录并修改，然后设置：
   ```env
   REPORT_RENDERER_ENABLED=true
   REPORT_TEMPLATES_DIR=./custom_templates
   ```
4. **通知渠道定制**：使用 `CUSTOM_WEBHOOK_URLS` + `CUSTOM_WEBHOOK_BODY_TEMPLATE` 接入 Bark、钉钉、自建服务等任意 HTTP 端点。

**适用边界**：策略 YAML 只能影响 LLM 的分析视角与文字输出，不能真正计算新指标；报告模板只能重排既有字段，不能增加新指标数据。

**验收标准**：新增策略后，Agent/分析报告中出现对应策略视角；自定义模板渲染成功；Webhook 收到符合预期的 payload，且核心代码零改动。

---

### 建议二（中期，最高 ROI）：做“指标插件 + Prompt Profile”两层能力

**目标**：用最小侵入补齐两个最大缺口——可靠的自定义指标计算，以及可组合的 Prompt 扩展。

**做法**：

1. **指标插件 SDK**
   - 新增 `src/plugins/`（manifest / loader / registry / context / api）。
   - 定义 `IndicatorPlugin` 协议：`compute()` 计算列、`summarize()` 输出摘要、`prompt_section()` 生成 Prompt 片段、`alert_evaluate()` 可选支持告警。
   - 在 `pipeline._enhance_context()` 写入 `enhanced["custom_indicators"]`。
   - 在 `analyzer._format_prompt()` 追加自定义指标区块。
   - `AnalysisResult` 增加可选 `custom_indicators` 字段，模板与前端按需展示。
   - 配置示例：
     ```env
     PLUGINS_ENABLED=true
     PLUGIN_DIRS=./plugins
     PLUGIN_ALLOWLIST=obv_indicator,atr_indicator
     CUSTOM_INDICATORS=obv,atr
     CUSTOM_INDICATOR_PARAMS={"obv":{"window":20},"atr":{"window":14}}
     ```
   - 以 OBV 插件作为首个示例（计算 OBV、OBV 均线、顶/底背离），验证“只加插件目录 + 环境变量即可生效”。

2. **Prompt Profile（可组合 Prompt，而不是裸 Prompt）**
   - 新增 `PromptSectionPlugin` 协议，按 `position` 插入系统提示词或用户提示词的指定锚点。
   - 新增 `PROMPT_PROFILE` + `PROMPT_PROFILE_DIR`，用 YAML 组合内置模板、插件段落与自定义文本。
   - 安全约束：只允许追加、不允许替换核心 JSON 契约段；设置 `max_extra_chars` 硬上限；段落顺序固定以保护 Prompt Cache。
   - 配置示例：
     ```env
     PROMPT_PROFILE=my_profile
     PROMPT_PROFILE_DIR=./prompts/profiles
     ```

**改造点清单**：

| 文件 | 改造 |
|---|---|
| `src/plugins/`（新增） | manifest / loader / registry / context / api |
| `src/config.py` | 新增插件与指标配置字段及 env 解析 |
| `src/core/config_registry.py` | 新增 `plugins` 分类，Web 设置页可见 |
| `src/core/pipeline.py:1084` | 注入 `custom_indicators` |
| `src/analyzer.py:4353` | `_format_prompt()` 追加自定义指标区块 |
| `src/analyzer.py:1732` | `AnalysisResult` 增加 `custom_indicators` 并写入 `to_dict()` |
| `templates/report_markdown.j2` | 渲染自定义指标区块 |
| `src/services/alert_indicators.py:14` | 改为注册表分发，新增通用 `indicator_threshold` 告警类型 |
| `src/services/screening/scorer.py:7` | 因子映射改为注册表查询，允许插件因子 |
| `data_provider/base.py:1794` | 加载外部 `DataProviderPlugin` |
| `api/v1/schemas/analysis.py:34` | 可选增加 `prompt_profile`，不暴露 raw prompt |

**适用边界**：指标插件需要在进程内运行，必须做异常隔离、超时与长度预算；Prompt Profile 不开放任意 raw prompt，以保护 JSON 输出契约与缓存稳定性。

**验收标准**：
- 只新增插件目录与环境变量，OBV 指标就能出现在分析 Prompt 和报告中。
- 插件关闭时，现有测试与行为完全不变。
- 单个插件异常时分析继续完成，并在 `data_limitations` 中记录降级原因。
- 指标计算对单股分析增加的耗时不超过 200ms。

---

### 建议三（长期）：补齐插件生态与治理

**目标**：把扩展能力从“指标 + Prompt”扩展到数据源、选股因子、告警、通知与 Agent 工具，并建立可运维的插件治理体系。

**做法**：

1. **数据源插件**：定义 `DataProviderPlugin`（`create_fetcher()` + `markets` + `priority`），在 `DataFetcherManager._init_default_fetchers()` 中加载；统一超时、重试、限流、健康检查与字段校验，失败自动降级。
2. **选股因子插件**：把 `FACTOR_SCORE_FUNCTIONS` 改为注册表，插件返回 0-100 分；YAML 中可直接引用插件因子名。
3. **告警插件**：新增通用 `indicator_threshold` 规则，按 `plugin + params` 调用插件评估；插件异常返回 `degraded`，不影响其他规则。
4. **通知插件**：定义 `NotificationChannelPlugin.send(title, content, meta)`，注册进 `NotificationService`；配合 allowlist 使用。
5. **Agent 工具插件**：通过 `dsa.plugins` entry point 返回 `ToolDefinition`，启动时注册到 `ToolRegistry`，并强制声明 `read_only / timeout / permissions`。
6. **治理体系**：
   - Manifest 规范：`api_version / name / version / type / entry / requires / permissions / config_schema`。
   - 发现机制：`entry_points(group="dsa.plugins")` + 本地目录扫描。
   - 安全：显式 allowlist、不自动下载、不远程执行；插件与主程序同等信任，需自行审查。
   - 可观测：插件加载日志、耗时指标、失败隔离、`/api/v1/plugins` 状态接口。
   - 兼容：`PLUGIN_API_VERSION` + `requires.app` + CI 契约测试。

**建议排期**：

| 阶段 | 内容 | 预计 |
|---|---|---|
| P0 | 用满现有扩展点（策略/选股/模板/Webhook） | 1 天 |
| P1 | 指标插件 SDK + OBV/ATR 示例 | 1 周 |
| P2 | Prompt Profile + Section 插件 | 1 周 |
| P3 | 选股因子 + 告警插件 | 1 周 |
| P4 | 数据源插件 + 插件治理与文档 | 1 周 |

**适用边界**：长期方案会引入插件加载、版本兼容与安全审查成本，建议在 P1/P2 验证真实需求后再推进，避免过度设计。

**验收标准**：第三方可在不 fork 主仓库的情况下发布一个 `dsa.plugins` 包，完成数据源/指标/通知任一扩展；主仓库升级不破坏已声明兼容的插件；插件故障不影响主流程。

---

## 六、总体建议

1. **先零代码，后 SDK**：优先用策略 YAML、选股 YAML、Jinja2 模板和 Webhook 解决当前需求，验证真实痛点。
2. **中期聚焦两层**：指标插件 + Prompt Profile 是投入产出比最高的组合，可同时解决“自定义指标”和“自定义 Prompt”。
3. **长期再生态化**：数据源、选股因子、告警、通知、Agent 工具插件化，并配套 manifest、allowlist、健康检查与版本契约。

> 备注：本评估基于 GitHub `main` 分支当前源码。若仓库后续重构了 Prompt 拼装、指标计算或注册表结构，文中行号与文件路径需同步复核。
