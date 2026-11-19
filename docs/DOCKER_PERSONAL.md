# Docker / NAS 部署（个人扩展层）

> 功能怎么用看 [个人扩展使用手册](USER_GUIDE_PERSONAL.md)；本文只讲部署。

本 fork 的个人扩展层已经打进 DSA 镜像：Web 页面在 `/personal`，个人 API 在
`/personal-api/*`。Docker 构建使用仓库根目录作为 context，前端在镜像构建阶段
由 `apps/dsa-web` 自动打包，不需要在 NAS 上装 Node。

> QMT 桥是 Windows-only，**不能**运行在 NAS 容器里。NAS 负责数据、回测、报告和
> Web 页面；QMT 实盘/行情桥仍需在 Windows 机器上单独运行。

> **同花顺截图 OCR：** 镜像内置 RapidOCR ONNX 模型和 OpenCV/ONNX 运行库，识别在
> 容器内 CPU 完成，不上传云端；镜像因此增加约 100MB+。首次识别会初始化模型，
> 之后常驻内存。若 NAS 内存很紧，可设 `PERSONAL_OCR_ENABLED=false`，在页面用
> 「手工录入」录账户快照。

## 1. 前置条件

- NAS 支持 Docker / Docker Compose（Synology DSM、QNAP Container Station 等）
- 架构：x86_64 或 arm64（上游基础镜像支持；arm64 构建时间更长）
- 内存：建议 **2GB+**（完整分析 + 回测）；最低 1GB
- 仓库放在 NAS 的本地卷（ext4/btrfs），**不要**把 `data/` 放在 SMB/NFS 网络盘上

## 2. 准备配置

```bash
git clone https://github.com/maochunguang/daily_stock_analysis.git
cd daily_stock_analysis

cp .env.example .env
```

编辑 `.env`，至少确认：

```env
# 上游分析所需（至少一个模型 Key）
OPENAI_API_KEY=...
# 或 GEMINI_API_KEY / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY ...

# 自选股
STOCK_LIST=600519,000001,510050

# 个人扩展层
PERSONAL_API_ENABLED=true
PERSONAL_STOCK_LIST=600519,000001,510050
PERSONAL_DATA_SOURCE_PRIORITY=tushare,baostock,akshare,tencent
TUSHARE_TOKEN=...

# 个人库/上游库（容器内路径；保持默认即可）
PERSONAL_UPSTREAM_DB=/app/data/stock_analysis.db
PERSONAL_DB=/app/data/personal.db
PERSONAL_DATA_DIR=/app/data
PERSONAL_PLUGIN_DIRS=/app/plugins
PERSONAL_BACKTEST_ADJUST=hfq
PERSONAL_CROSS_SOURCE_CHECK=true

# QMT（NAS 上不可用，指向 Windows QMT 机器；不填则 QMT 页面显示未连接）
# QMT_BRIDGE_URL=http://192.168.1.50:8710
# QMT_BRIDGE_TOKEN=change-me
QMT_TRADING_ENABLED=false
QMT_REQUIRE_CONFIRM=true
```

> `config/personal.env` 是可选的本地文件配置；Docker 部署推荐直接用 `.env`
> 环境变量，避免把配置文件挂进容器。

## 3. 启动

```bash
# 只启动 Web/API（推荐；定时分析可另开 analyzer 或使用上游 schedule）
docker compose -f docker/docker-compose.yml up -d server

# 查看日志
docker compose -f docker/docker-compose.yml logs -f server
```

访问：

- 个人扩展页：[http://NAS_IP:8000/personal](http://NAS_IP:8000/personal)
- 上游首页：[http://NAS_IP:8000/](http://NAS_IP:8000/)
- 个人 API 健康检查：[http://NAS_IP:8000/personal-api/api/health](http://NAS_IP:8000/personal-api/api/health)
- 上游 API 文档：[http://NAS_IP:8000/docs](http://NAS_IP:8000/docs)

端口由 `.env` 的 `API_PORT` 控制（默认 8000）。如果宿主机 8000 已被其他服务占用，
用环境变量覆盖即可（Compose 的 shell 环境变量优先级高于 `.env`）：

```bash
API_PORT=8010 docker compose -f docker/docker-compose.yml up -d server
# 访问 http://NAS_IP:8010/personal
```

## 4. 数据持久化

Compose 默认挂载：

| 宿主机 | 容器 | 内容 |
|---|---|---|
| `./data` | `/app/data` | 上游库 `stock_analysis.db`、个人库 `personal.db`、缓存 |
| `./logs` | `/app/logs` | 日志 |
| `./reports` | `/app/reports` | 报告 |
| `./strategies` | `/app/strategies` | 策略 YAML（只读） |

个人库和上游库在同一个 `data/` 卷中，但文件分离：

```text
data/stock_analysis.db   # 上游库（个人层只读）
data/personal.db         # 个人库（读写）
```

**SQLite 注意事项**：

- 使用 NAS 本地卷（ext4/btrfs）或 Docker named volume。
- 不要放在 SMB/CIFS/NFS 挂载点上运行 SQLite，WAL 锁可能不可靠。
- 备份时至少备份 `data/personal.db`、`data/stock_analysis.db`、`config/`。

## 5. ARM64 / x86_64

- 上游基础镜像 `node:20-slim`、`python:3.11-slim-bookworm` 均有多架构版本。
- 在 NAS 上直接 `docker compose build` 会按本机架构构建。
- 如果在 x86 机器上为 ARM NAS 构建：

  ```bash
  docker buildx build --platform linux/arm64 \
    -f docker/Dockerfile -t dsa-personal:arm64 .
  ```

- 若 NAS 是 ARM 且构建 `wkhtmltopdf` 很慢，可以只启动 `server` 服务，不构建桌面端。

## 6. 更新

```bash
git pull
docker compose -f docker/docker-compose.yml build server
docker compose -f docker/docker-compose.yml up -d server
```

如果上游更新改动了 `api/app.py`、`apps/dsa-web/src/*` 等 UI 集成文件，需要重新
应用补丁：

```bash
git apply --check patches/0001-personal-web-integration.patch
git apply patches/0001-personal-web-integration.patch
cd apps/dsa-web && npm run build
```

（如果补丁已经包含在 fork 的最新提交里，则只需重新 build 镜像。）

## 7. 认证与安全

- 建议开启上游管理员认证：

  ```env
  ADMIN_AUTH_ENABLED=true
  ```

  开启后 `/personal-api/*` 也会受同一套登录会话保护。
- 不要把 8000 端口直接暴露到公网；通过 NAS 反向代理 + HTTPS + 访问控制。
- `QMT_TRADING_ENABLED` 保持 `false`；NAS 只做分析/回测，不执行交易。
- 不要把 `.env`、`config/personal.env`、`data/*.db` 提交到 Git。

## 8. 故障排查

| 现象 | 检查 |
|---|---|
| `/personal` 页面空白 | 确认镜像构建时包含 `apps/dsa-web` 最新代码；看容器日志是否有前端资源缺失 |
| `/personal` 能打开但数据不显示 | 访问 `/personal-api/api/status`；确认 `PERSONAL_API_ENABLED=true`，镜像包含 `personal/` |
| `/personal-api` 404 | 检查 `upstream/api/app.py` 的挂载是否在 SPA catch-all 之前；重新构建镜像 |
| 数据库只读/无法写入 | 检查 `./data` 权限；entrypoint 会尝试 chown 到 UID 1000；避免只读/NFS 挂载 |
| 个人库丢失 | 确认 `PERSONAL_DB=/app/data/personal.db` 且 `./data` 已挂载 |
| QMT 页面显示未连接 | NAS 容器无法运行 Windows QMT；配置 `QMT_BRIDGE_URL` 指向 Windows 机器 |
| ARM64 构建失败 | 检查基础镜像是否支持该架构；优先在 NAS 本机构建 |
| 启动时报端口被占用 | 宿主机 8000 被其他进程占用；用 `API_PORT=8010 docker compose ... up -d server` |
| 构建很慢（>10 分钟） | `wkhtmltopdf` 的 Qt 依赖较大属正常现象；首次构建后走 Docker 层缓存会快很多 |

## 9. NAS 实际部署布局（2026-11-18 固化，更新不丢数据）

UGREEN NAS（x86_64）实际部署与 compose 示例略有不同，以本节为准：

| 项 | 值 |
|---|---|
| 项目目录 | `/volume2/docker/daily_stock_analysis/` |
| 持久化 | `data/ logs/ reports/ .env`（bind 挂载 + 本地文件，重建容器不丢）；WebUI 配置在 `data/runtime.env` |
| 部署清单 | `docker-compose.yml`（同目录，含 server + personal-sync 两服务） |
| 镜像 | `dsa-fork:latest`（本地 buildx amd64 构建，scp 传输） |
| 访问 | `http://NAS_IP:18800/personal` |
| 容器 | `daily_stock_analysis-2`（上游 `--schedule` 模式）+ `stock-personal-sync`（个人层 06:00/12:00/18:00 三轮同步 + 数据体检） |

**更新镜像三步（数据/配置零丢失）：**

```bash
# 本机（Mac，arm64 -> amd64 交叉构建）
docker buildx build --platform linux/amd64 -t dsa-fork:latest --load -f docker/Dockerfile .
docker save dsa-fork:latest | gzip > /tmp/dsa-fork-amd64.tar.gz
scp -O -P 931 /tmp/dsa-fork-amd64.tar.gz <user>@<NAS_IP>:~/

# NAS（SSH；SFTP 受限必须 scp -O）
docker load -i ~/dsa-fork-amd64.tar.gz
cd /volume2/docker/daily_stock_analysis && docker compose up -d --force-recreate
```

`personal.db`、`stock_analysis.db`、`.env`、阿姆氏快照目录 `data/arms_daily/`
都在 bind 挂载里，`--force-recreate` 只换容器不碰数据。容器配置以
`docker-compose.yml` 为准（含 `NEWS_INTEL_ALLOW_PRIVATE_HOSTS` 等），**不要再
手工 `docker run`**，改配置直接编辑 compose 文件后 `docker compose up -d`。

`TUSHARE_TOKEN` 从项目目录 `.env` 由 compose 变量替换注入 personal-sync。

> **personal-sync 也必须设置 `ENV_FILE=/app/data/runtime.env`。** 该服务独立于
> server，若只给 server 设置，定时任务读不到 WebUI 的 `STOCK_LIST`，日线/状态/
> 复权同步会显示 0 行。2026-11-19 已在 NAS compose 中补齐并验证 13 只自选股
> 入库（备份 `docker-compose.yml.bak-20261119-bars`）。

### WebUI 配置（LLM 密钥 / 自选股）持久化

**事故原因（2026-11-18 修复）**：上游把 WebUI 保存的配置写入 `ENV_FILE`
（默认 `/app/.env`），该路径在容器可写层，`docker compose up --force-recreate`
后连同镜像层一起被丢弃——所以 LLM 密钥、自选股会偶发“消失”。宿主机 `.env`
之前只被 compose 用于 `${VAR}` 替换，并没有注入或挂载进容器。

**现行做法（与上游官方建议一致）**：

| 项 | 值 |
|---|---|
| 活跃配置文件 | `ENV_FILE=/app/data/runtime.env`（在 `data/` bind 挂载里） |
| 首次迁移 | `cp .env data/runtime.env && chmod 600 data/runtime.env` |
| 配置来源 | 之后以 WebUI 保存为准；宿主机 `.env` 只保留 compose 变量（如 `TUSHARE_TOKEN`） |
| 禁止 | 不要把宿主机 `.env` 单文件挂载到 `/app/.env`（Docker mount point 会阻止原子替换） |

容器内确认：

```bash
docker exec daily_stock_analysis-2 sh -c 'echo $ENV_FILE; ls -l /app/data/runtime.env'
docker exec -i daily_stock_analysis-2 python - <<'PY'
from src.config import Config
c = Config.get_instance()
print(len(c.stock_list), len(c.llm_channels or []), c.litellm_model)
PY
```

重建容器后上面三个值应保持不变。若某键同时存在于宿主机 compose 的
`env_file`/`environment`，启动环境变量会覆盖 `runtime.env`，需要从启动配置里移除同名键。

数据体检（RM-41）部署到已运行环境时，需要一次性修复历史快照（老版本把
06:00 抓到的上一交易日数据标成了当天，并把 ETF 份额按「份」入库）：

```bash
docker exec -i daily_stock_analysis-2 python - <<'PY'
import sqlite3
c = sqlite3.connect("/app/data/personal.db")
c.execute("DELETE FROM etf_share")                 # 单位错误 + 日期错位
c.execute("DELETE FROM sector_amount")             # 日期错位（仅 1 天快照）
c.execute("DELETE FROM limit_up_stats WHERE trade_date >= date('now','localtime')")
c.commit()
PY
docker exec daily_stock_analysis-2 python -m personal.cli.main sync --dataset sector
docker exec daily_stock_analysis-2 python -m personal.cli.main sync --dataset etf_share
docker exec daily_stock_analysis-2 python -m personal.cli.main sync --dataset calendar \
  --start 2024-01-01 --end 2026-12-31          # 交易日历回填，校验/缺口检查依赖
docker exec daily_stock_analysis-2 python -m personal.cli.main validate
```

数据源限制（回填时的实测结论）：

- 东财涨停/炸板/昨涨停池只能回溯 **30 个交易日**，更早的历史无法回补
- 行业拥挤度（同花顺行业成交额）与宽基 ETF 份额是**当日快照接口**，
  无历史可回补，序列从启用日起自建积累
- Tushare 免费档 `opt_basic`/`opt_daily` 限频 **1 次/小时**（所以 PCR 用
  上交所官方统计接口，见 §7.7）
- 乐咕乐股指数估值免费档只提供**周频**历史（日线为付费功能）；`valuation`
  数据集每次拉全量并按 ISO 周去重，见使用手册 §4.6
- 指数估值的官方交叉校验按需请求中证/国证接口；失败只把对应指数标为
  `不可用`，不影响估值卡片、定时同步或本地历史分位
- 长区间回填受 `MARGIN_MAX_DAYS=120` 保护，按 ≤120 天分块

## 10. 最小验证命令

```bash
curl -f http://127.0.0.1:8000/api/health
curl -f http://127.0.0.1:8000/personal-api/api/health
curl -s http://127.0.0.1:8000/personal-api/api/status | head
```

## 10. 本机验证记录（macOS arm64）

2026-11-16 在 Docker Desktop for Mac（linux/aarch64，12 CPU / 8GB）上完成了真实
构建、启动和页面验证：

```bash
docker --version                 # 29.9.3
docker compose version           # v5.7.0
cp .env.example .env             # 本地测试用，.env 已被 gitignore

docker compose -f docker/docker-compose.yml build server
# => daily-stock-analysis-server:latest, 2.36GB

API_PORT=8010 docker compose -f docker/docker-compose.yml up -d server
docker ps                        # stock-server ... Up (healthy)
```

验证结果：

| 检查项 | 结果 |
|---|---|
| 构建时 `RUN python -c "import personal.api.app"` | ✅ |
| 启动日志 `Personal extension API mounted at /personal-api` | ✅ |
| `GET /api/health` | ✅ 200 |
| `GET /personal-api/api/health` | ✅ `{"ok":true,"version":"0.1.0"}` |
| `GET /personal-api/api/status` | ✅ 返回 `/app/data/personal.db`、`/app/data/stock_analysis.db` |
| `GET /personal` | ✅ 200，返回 SPA |
| 浏览器打开 `/personal` | ✅ 上游左侧栏含「个人扩展」，总览/回测/插件标签正常 |
| 页面内运行 Demo 回测 | ✅ 指标、净值曲线、45 条交易明细正常渲染 |
| ARM64 NumPy/pandas | ✅ 无 OpenBLAS SIGILL |
| 保存回测后 `docker restart` | ✅ `demo-b7668fe7044f` 仍可查询 |
| 插件加载 | ✅ `obv` 1 个，无错误 |
| 容器日志 | ✅ 无 traceback/mount 失败 |

说明：

- 容器内数据库路径是 `/app/data/*.db`，对应宿主机 `./data/*.db`（bind mount）。
- 首次构建约 10 分钟，主要耗时在 `wkhtmltopdf` 的 Qt 依赖和 pip 安装；后续改动
  只要不触碰这些层，会走缓存。
- 测试机上宿主机 8000 被其他服务占用，所以用 `API_PORT=8010` 验证；NAS 上按实际
  端口调整即可。
- 上游库 `stock_analysis.db` 在第一次上游分析前不存在，页面显示「上游 DSA 未生成」
  属于预期行为。
