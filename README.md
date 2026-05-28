# QQ Music Downloader

QQ 音乐下载工具 — 搜索、歌单批量下载、VIP 歌曲下载、多音源自动回退、AI 发现新音源。
提供 Web GUI（FastAPI + 原生 JS）和 CLI 两种界面，页面秒开无需等待。

## 下载

| 平台 | 下载 |
|------|------|
| macOS (Apple Silicon) | [QQMusicDL-macOS-arm64.zip](https://github.com/dylan121322/qqmusic-dl/releases/latest) |
| Windows (x64) | [QQMusicDL-Windows-x64.zip](https://github.com/dylan121322/qqmusic-dl/releases/latest) |

> 点开即用，无需安装 Python。解压后双击 `QQMusicDL` 即可。
>
> **macOS 用户**：若提示「无法验证是否包含恶意软件」，在终端执行以下命令后即可打开：
>
> ```bash
> xattr -dr com.apple.quarantine /path/to/QQMusicDL   # 将解压后的 QQMusicDL 文件拖入终端即可自动填入路径
> ```

## 功能

- 关键词搜索 + 歌单批量下载（含短链接）
- 多平台登录：QQ 音乐 / 网易云 / 酷狗（标签切换，独立 Cookie）
- Chrome CDP 一键自动提取 Cookie（含 HttpOnly）
- 网易云登录后自动解锁 VIP 歌曲 + 320kbps 音质
- 多音源自动回退：QQ 音乐 → 网易云 → 酷狗 → 网络搜索
- AI 音源发现：自动搜索互联网 + AI 分析网页 + 注册新音源
- 3 层下载回退：主音源 → 已知音源 → 针对性网页搜索
- 多线程下载 + 进度条
- 320kbps / FLAC 音质选择

## 安装

```bash
cd qqmusic-dl
pip install -r requirements.txt
pip install websocket-client cryptography
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
4. 粘贴歌单链接 → **获取歌单** → 勾选 → 下载

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
qqmusic-dl/
├── server.py           # FastAPI 后端 + 静态文件服务（Web 入口）
├── launcher.py         # 打包入口（PyInstaller 构建用）
├── static/             # 前端页面（原生 HTML/CSS/JS，零依赖）
│   ├── index.html      # 单页应用（含多平台登录）
│   └── style.css       # 暗色主题
├── .github/workflows/  # CI 自动构建（macOS + Windows）
├── app.py              # [旧] Streamlit Web GUI
├── main.py             # CLI 入口
├── api.py              # QQ 音乐 API + CDP HTML 歌单提取
├── downloader.py       # 多线程下载引擎 + 3层回退
├── models.py           # Song 数据模型
├── utils.py            # 工具函数、Cookie 解析、g_tk 计算
├── cdp_cookies.py      # Chrome CDP Cookie 提取（含 HttpOnly）
├── login.py            # 二维码登录（QQ）
├── browser_login.py    # 浏览器 Cookie 读取 + Chrome Keychain 解密
├── receiver.py         # 本地 HTTP 接收器
├── requirements.txt
└── sources/            # 多音源系统
    ├── __init__.py     # 音源注册中心 + 回退逻辑
    ├── base.py         # MusicSource 抽象基类
    ├── netease.py      # 网易云音乐
    ├── kugou.py        # 酷狗音乐
    ├── template.py     # JSON 模板音源（零代码添加新源）
    ├── discovery.py    # 网页爬取 + 自动发现
    ├── ai_discovery.py # AI 发现引擎（搜索→访问→分析→注册）
    └── configs/        # 自动保存发现的音源模板 JSON
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

`~/.config/qqmusic-dl/config.json`：

```json
{
  "download_dir": "~/Music/QQMusic",
  "quality": "320kbps",
  "workers": 3,
  "accounts": {
    "qq": "uin=...; qqmusic_key=...",
    "netease": "MUSIC_U=...",
    "kugou": "kg_mid=..."
  }
}
```

## 依赖

- Python 3.8+
- fastapi, uvicorn, requests, rich
- websocket-client, cryptography
- Google Chrome（CDP Cookie 提取需要）

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
| [react-icons](https://github.com/react-icons/react-icons) | MIT |
| [pptxgenjs](https://github.com/gitbrent/PptxGenJS) | MIT |

## 注意

- 本工具仅供**个人备份**使用，请遵守相关法律法规
- Cookie 有时效性（约 2-3 天），过期后需重新登录
- CDP Chrome 端口默认 9233，需保持 Chrome 运行
- 歌单提取依赖 CDP Chrome，确保 Chrome 未被完全关闭
