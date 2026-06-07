# Music DL

多平台音乐下载工具 — 聚合搜索、歌单批量下载、多音源自动回退、AI 音源发现、网页搜索兜底。
提供 Web GUI（FastAPI + 原生 JS）和 Android 原生 App（Java + Chaquopy）。

## 下载

| 平台 | 下载 |
|------|------|
| Android APK | [app-debug.apk](https://github.com/dylan121322/music-dl-android/releases/tag/v1.5.1) |
| macOS (Apple Silicon) | [MusicDL-macOS-arm64.zip](https://github.com/dylan121322/music-dl/releases/latest) |
| Windows (x64) | [MusicDL-Windows-x64.zip](https://github.com/dylan121322/music-dl/releases/latest) |

> 点开即用，无需安装 Python。解压后双击 `MusicDL` 即可。
>
> **macOS 用户**：若提示「无法验证是否包含恶意软件」，在终端执行以下命令后即可打开：
>
> ```bash
> xattr -dr com.apple.quarantine /path/to/MusicDL   # 将解压后的 MusicDL 文件夹拖入终端即可自动填入路径
> ```

## 功能

- **聚合搜索**：同时搜索 QQ音乐 + 网易云 + 酷狗 + GitHub，结果去重合并，显示来源标签
- **Android 原生 App**：Material You 风格，AMOLED 纯黑 + 紫色点缀，大卡片 + 来源色条
- **内置播放器**：Native MediaPlayer，音频焦点管理，拔出耳机自动暂停
- **下载源选择**：自动 / QQ / 网易云 / 酷狗 / GitHub / 网页搜索
- **多引擎网页搜索**：Bing + DuckDuckGo 并行搜索，AI 智能排序候选页面
- **三层下载回退**：主音源 → 备选音源（精确歌名优先）→ 网页搜索（AI 辅助）
- **AI 音源发现**：支持 DeepSeek / OpenAI / Claude，自动搜索 + 分析网页 + 注册新音源
- **LX Music 兼容**：支持导入洛雪音乐 JS 音源（纯 Python 解析，无需 Node.js）
- **FLAC 无损**：QQ音乐/网易云/酷狗均支持 FLAC 音质（需登录）
- **链接下载**：粘贴任意音乐链接，规则 + AI 两级提取音频 URL，自动下载
- **运行时日志**：自动轮转日志文件（5MB×3），JSON/TXT 导出 API
- 多平台登录：QQ 音乐 / 网易云 / 酷狗（标签切换，独立 Cookie）
- Chrome CDP 一键自动提取 Cookie（含 HttpOnly）
- 未登录自动回退到免费音源，不卡等待
- 暂停/恢复登录（调试用）

---

## LX Music 音源兼容

支持导入洛雪音乐的 JS 音源文件，纯 Python 解析，无需 Node.js。

**使用方式**：
1. 将 `.js` 音源文件放入 `~/.config/music-dl/lx_sources/` 目录
2. 重启应用，音源自动加载并加入搜索和下载回退链
3. 或点击侧边栏「导入 LX 音源」手动加载

## 安装

### 桌面端 (macOS / Windows / Linux)

```bash
cd music-dl
pip install -r requirements.txt
# Chrome CDP Cookie 提取需要：
pip install websocket-client cryptography
```

### Android

**方式 A: APK 直接安装**
从 [Releases](https://github.com/dylan121322/music-dl/releases) 下载最新 APK，直接安装。

**方式 B: 自行构建**
```bash
cd android
# Windows: powershell -File build_full.ps1
# macOS/Linux: bash build_apk.sh
# 需要 Android SDK + JDK 17+ + Python 3.12
```

> APK 使用 Chaquopy 嵌入 Python 运行时，原生 Java UI（Material You 设计），支持音频焦点管理、耳机拔出检测、StrictMode 调试。

### 桌面端独立窗口（可选）

```bash
python launcher.py             # 内置 WebView 窗口，无需打开浏览器
```

## 快速开始

### Web GUI（推荐）

```bash
python server.py
# 打开 http://localhost:8765
```

1. 侧边栏 → **🔑 登录** → 选择平台（QQ/网易云/酷狗）
2. **打开Chrome** → 在打开的页面微信/QQ扫码登录
3. **提取Cookie** → 自动从 Chrome CDP 读取并保存
4. 搜索歌曲 → 勾选 → 选择下载源 → **下载选中**

### 下载源说明

| 源 | 说明 |
|------|------|
| 自动 | 已登录优先 QQ，未登录自动回退免费源 |
| QQ | 仅使用 QQ 音乐 |
| 网易云 | 仅使用网易云音乐 |
| 酷狗 | 仅使用酷狗音乐 |
| 网页 | 跳过音乐平台，直搜 mp3 站 + AI 分析 |

### AI 配置（网页搜索和音源发现需要）

侧边栏 → 🤖 AI 发现音源：
1. 选择模型（DeepSeek / OpenAI / Claude）
2. 填入模型名称、API Key、Base URL
3. 点击「保存 AI 配置」

### CLI

```bash
# 登录
python main.py login

# 搜索
python main.py search "晴天"

# 歌单下载
python main.py dl "https://c6.y.qq.com/base/fcgi-bin/u?__=TOKEN"
python main.py dl "https://y.qq.com/n/ryqq/playlist/123456.html"

# 设置
python main.py config
python main.py config --dir ~/Music
```

## 多平台登录

侧边栏提供三个平台的登录标签：

| 平台 | 登录方式 | Cookie 关键字段 | 登录后作用 |
|------|---------|----------------|------------|
| QQ 音乐 | 微信/QQ 扫码 | `qqmusic_key` / `qm_keyst` | VIP 歌曲 + 收藏下载 |
| 网易云音乐 | 微信/QQ/手机扫码 | `MUSIC_U` | VIP 歌曲 + 320kbps |
| 酷狗音乐 | 手机扫码 | 通用 | 备用音源下载 |

> CDP Cookie 提取对三个平台通用：打开对应网站 → 手动登录 → 点「提取Cookie」

## 歌单链接格式

| 格式 | 示例 |
|------|------|
| 短链接 | `c6.y.qq.com/base/fcgi-bin/u?__=...` |
| 歌单页 | `y.qq.com/n/ryqq/playlist/123456.html` |
| 分享页 | `i.y.qq.com/n2/m/share/details/taoge.html?id=...` |
| 纯数字 | `9718789079` |

## 音质选项

| 选项 | 码率 | 格式 |
|------|------|------|
| `128kbps` | 128kbps | M4A |
| `320kbps` | 320kbps | MP3 |
| `flac` | 无损 | FLAC |

## 项目结构

```
music-dl/
├── server.py               # FastAPI App 组装 (69行)
├── server_models.py        # Pydantic 请求/响应模型
├── server_state.py         # 状态管理: get_api(Lock), lifespan(TTL清理)
├── server_routes_config.py # 配置端点 (5个)
├── server_routes_search.py # 多平台并行搜索+去重
├── server_routes_download.py # 下载/流/播放/进度SSE (7端点)
├── server_routes_auth.py   # CDP登录/源管理/日志 (10端点)
├── launcher.py             # 桌面窗口启动器（PyInstaller 构建用）
├── logger.py               # 统一日志引擎（RotatingFileHandler, 5MB×3）
├── exporter.py             # 日志导出（JSON/TXT/日期筛选）
├── link_extractor.py       # 链接音频提取（规则 + AI 两级）
├── static/                 # Web 前端（原生 HTML/CSS/JS，零依赖）
│   ├── index.html          # 单页应用（多平台搜索 + 下载 + 播放）
│   └── style.css           # 暗色主题
├── android/                # Android App（Chaquopy Python-in-Android）
│   └── app/src/main/java/com/musicdl/MainActivity.java  # 原生 Java UI
├── tests/                  # 测试套件（pytest + httpx）
│   ├── conftest.py         # 测试 fixtures
│   ├── test_api.py         # API 端点测试
│   ├── test_utils.py       # 工具函数测试
│   ├── test_logger.py      # 日志引擎测试
│   └── test_exporter.py    # 导出模块测试
├── .opencodereview/        # 代码审查规则
│   └── rule.json           # 按扩展名匹配审查规则
├── pyproject.toml          # Pytest 配置
├── .github/workflows/      # CI 自动构建（macOS + Windows）
├── main.py                 # CLI 入口
├── api.py                  # QQ 音乐 API + CDP HTML 歌单提取
├── downloader.py           # 多线程下载引擎 + 3层回退
├── models.py               # Song 数据模型
├── utils.py                # 工具函数、Cookie 解析、g_tk 计算、AI 配置
├── cdp_cookies.py          # Chrome CDP Cookie 提取（含 HttpOnly）
├── login.py                # 二维码登录（QQ）
├── browser_login.py        # 浏览器 Cookie 读取 + Chrome Keychain 解密
├── requirements.txt
└── sources/                # 多音源系统
    ├── __init__.py          # 音源注册中心 + 回退逻辑
    ├── base.py              # MusicSource 抽象基类
    ├── netease.py           # 网易云音乐
    ├── kugou.py             # 酷狗音乐
    ├── github.py            # GitHub 音源
    ├── lx_adapter.py        # LX Music JS 音源适配器
    ├── template.py          # JSON 模板音源（零代码添加新源）
    ├── discovery.py         # 网页爬取 + 自动发现
    ├── ai_discovery.py      # AI 发现引擎（搜索→访问→分析→注册）
    └── configs/             # 自动保存发现的音源模板 JSON
```

## 下载回退链路

```
下载请求
  ├─ ① QQ 音乐（主音源，VIP 需要登录）
  │   └─ 下载 ✅ / 失败 ↓
  ├─ ② 已知音源（网易云、酷狗、模板源、AI发现源）
  │   └─ 下载 ✅ / 失败 ↓
  └─ ③ 针对性网络搜索
      ├─ Bing 搜索 "{歌名} {歌手} mp3"
      ├─ 逐个打开结果页面
      ├─ 扫描 .mp3/.m4a 链接 + 测试可用性
      └─ 下载 ✅ / 跳过 ⏭
```

## AI 音源发现

侧边栏 → 🤖 AI 发现音源：

| 层级 | 方法 | 说明 |
|------|------|------|
| Phase 1 | 直接探测 | 向已知免费 API 域名发测试请求 |
| Phase 2 | 网络搜索 | Bing 搜索音乐 API |
| Phase 3 | 逐页分析 | 打开每个结果 → AI/规则分析 → 生成模板 |

| 分析引擎 | 需要 Key | 能力 |
|----------|---------|------|
| rule-based | 免费 | 自动识别 JSON API 字段映射、HTML 模式 |
| OpenAI | `sk-...` | LLM 理解任意页面结构 |
| Claude | `sk-ant-...` | LLM 理解任意页面结构 |

## 原理

- **歌单提取**：CDP 控制 Chrome 打开歌单页，解析嵌入的 `songList` JSON
- **Cookie 提取**：Chrome DevTools Protocol 读取所有 Cookie（含 HttpOnly）
- **下载链接**：调用 QQ 音乐 `GetVkey` 获取 CDN 地址
- **VIP 识别**：已登录自动跳过付费标记，VIP 歌曲直接下载
- **音源回退**：VIP 歌曲无账号时自动从网易云/酷狗/网络搜索替代
- **g_tk 计算**：`hash33(qqmusic_key)` — QQ 和微信登录均支持

## 配置文件

`~/.config/music-dl/config.json`：

```json
{
  "download_dir": "~/Music",
  "quality": "320kbps",
  "workers": 3,
  "accounts": {
    "qq": "uin=...; qqmusic_key=...",
    "netease": "MUSIC_U=...",
    "kugou": "kg_mid=..."
  }
}
```

## 运行时日志

应用自动记录日志到 `~/.config/music-dl/logs/music-dl.log`，5MB 自动轮转，保留 3 个备份。

```bash
# 查看日志统计
curl http://127.0.0.1:8765/api/logs/status

# 导出今日 JSON
curl -X POST http://127.0.0.1:8765/api/logs/export \
  -H "Content-Type: application/json" \
  -d '{"format":"json","date":"2026-06-01"}'

# 导出全文 TXT
curl -X POST http://127.0.0.1:8765/api/logs/export \
  -H "Content-Type: application/json" \
  -d '{"format":"txt"}'
```

## 测试

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v    # 65 tests (API / 工具函数 / 日志 / 导出 / 链接提取)
```

## 代码审查

集成阿里巴巴 [Open Code Review](https://github.com/alibaba/open-code-review) (OCR) CLI，确定性工程 + Agent 混合架构：

```
git diff → 文件筛选 → 模块打包 → 规则匹配 → OCR 系统性扫描 → 四Agent并行审查 → 行号校验/去重/分级
```

四 Agent 并行审查：Bug Scanner（安全/崩溃） + Code Reviewer（逻辑/测试覆盖） + UI/UX Checker + Devil's Advocate（设计决策）

审查规则按文件类型自动匹配 (`.opencodereview/rule.json`)：Python (None引用/异常/资源泄漏/线程安全/SQL注入/路径遍历) / HTML (XSS/escJs) / CSS (布局一致性) / JS (XSS/eval)

## 依赖

- Python 3.8+（Android 兼容）/ 桌面端 Python 3.10+
- fastapi, uvicorn, requests, rich
- websocket-client, cryptography
- Google Chrome（CDP Cookie 提取需要）

## API 参考

23 个 REST 端点，按模块组织：

| 模块 | 端点 | 方法 | 说明 |
|------|------|------|------|
| config | `/api/status` | GET | 登录状态、音质、下载目录 |
| config | `/api/config` | GET/POST | 配置读写 |
| config | `/api/config/ai` | GET/POST | AI 配置读写 |
| search | `/api/search` | POST | 聚合搜索 `{"keyword":"晴天","limit":20}` |
| download | `/api/play` | POST | 获取播放链接 `{"mid":"xxx","quality":"320kbps"}` |
| download | `/api/stream` | GET | 流式播放本地文件 `?path=...` |
| download | `/api/download` | POST | 批量下载 `{"songs":[...],"quality":"320kbps"}` |
| download | `/api/download/progress/{id}` | GET | SSE 下载进度 |
| download | `/api/downloads` | GET | 已下载文件列表 |
| download | `/api/playlist` | POST | 歌单提取 `{"url":"..."}` |
| download | `/api/link` | POST | 链接下载 `{"url":"...","quality":"320kbps"}` |
| auth | `/api/login/cookie` | POST | Cookie 登录 `{"cookie":"...","platform":"qq"}` |
| auth | `/api/login/chrome` | POST | 打开 Chrome 登录页 `?platform=qq` |
| auth | `/api/login/cdp` | POST | CDP 提取 Cookie `?platform=qq` |
| auth | `/api/login/suspend` | POST | 暂停登录 `?platform=qq` |
| auth | `/api/login/restore` | POST | 恢复登录 `?platform=qq` |
| auth | `/api/sources/discover` | POST | AI 发现音源 |
| auth | `/api/sources/status` | GET | 音源可用性检测 |
| auth | `/api/sources/lx/import` | POST | 导入 LX 音源 |
| auth | `/api/logs/status` | GET | 日志统计（行数/错误/警告/大小） |
| auth | `/api/logs/export` | POST | 导出日志 `{"format":"json"\|"txt","date":null}` |
| auth | `/debug/play` | GET | 播放诊断 |

### Android 专有端点 (music-dl-android)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/stream?url=` | GET | CDN URL 代理（白名单，无 Cookie 转发） |
| `/api/cache` | GET | CDN 音频缓存（域名校验 + Content-Type 验证） |
| `/api/favorites` | POST | QQ 音乐收藏列表 |

## 参考与致谢

本项目为原创实现，以下项目提供了 API 接口分析参考：

| 项目 | 作者 | License | 参考内容 |
|------|------|---------|----------|
| [qqmusicdownloader](https://github.com/yuqie6/qqmusicdownloader) | yuqie6 | — | 歌单/搜索 API 模块名 |
| [qq-music-api](https://github.com/copws/qq-music-api) | copws | — | musicu.fcg 接口格式 |
| [MCQTSS_QQMusic](https://github.com/huahuadiandian/MCQTSS_QQMusic) | huahuadiandian | — | 收藏 API 接口分析 |

### 第三方依赖 License

| 依赖 | License |
|------|---------|
| [fastapi](https://github.com/fastapi/fastapi) | MIT |
| [uvicorn](https://github.com/encode/uvicorn) | BSD |
| [requests](https://github.com/psf/requests) | Apache 2.0 |
| [rich](https://github.com/Textualize/rich) | MIT |
| [websocket-client](https://github.com/websocket-client/websocket-client) | Apache 2.0 |
| [cryptography](https://github.com/pyca/cryptography) | Apache 2.0 / BSD |
## 免责声明

本工具是一个基于 Python 的命令行和 Web 工具，可以从多个平台搜索和下载音乐。工具的本意是**聚合搜索**，方便寻找音乐，解决不知道哪个平台有版权的问题。API 均从公开网络中获得，**不是破解版**。

**禁止将本工具用于商业用途**，如产生法律纠纷与本人无关。

如有侵权，请联系我删除。

## 联系作者

- **GitHub Issues**：[提交 Issue](https://github.com/dylan121322/music-dl/issues)

---

## 使用提示

- Cookie 有时效性（约 2-3 天），过期后需重新登录
- CDP Chrome 端口默认 9233，需保持 Chrome 运行
- 歌单提取依赖 CDP Chrome，确保 Chrome 未被完全关闭
