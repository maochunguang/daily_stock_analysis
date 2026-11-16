# Docker / NAS 部署（个人扩展层）

> 功能怎么用看 [个人扩展使用手册](USER_GUIDE_PERSONAL.md)；本文只讲部署。

本 fork 的个人扩展层已经打进 DSA 镜像：Web 页面在 `/personal`，个人 API 在
`/personal-api/*`。Docker 构建使用仓库根目录作为 context，前端在镜像构建阶段
由 `apps/dsa-web` 自动打包，不需要在 NAS 上装 Node。

> QMT 桥是 Windows-only，**不能**运行在 NAS 容器里。NAS 负责数据、回测、报告和
> Web 页面；QMT 实盘/行情桥仍需在 Windows 机器上单独运行。

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

## 9. 最小验证命令

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
