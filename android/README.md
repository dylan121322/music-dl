# Music DL Android

Android 专版 — 基于 [music-dl](https://github.com/dylan121322/music-dl) 主线 fork，针对移动端深度优化。

## 与主线差异

| 项目 | 主线 | Android 专版 |
|------|------|-------------|
| 日志路径 | `~/.config/music-dl/logs/` | `/data/data/com.musicdl/files/logs/` |
| 配置路径 | `~/.config/music-dl/config.json` | `/data/data/com.musicdl/files/config.json` |
| 下载目录 | `~/Music/` | `/sdcard/Music/` |
| 静态文件 | 项目目录 `static/` | Python 源码目录 `static/` |
| UI | Web FastAPI | 原生 Java Material You |
| 播放器 | Web Audio | Android MediaPlayer |
| 日志策略 | 文件轮转 + 控制台 | 文件轮转 + logcat 双写 |

## 日志位置

```
/data/data/com.musicdl/files/logs/music-dl.log
```

通过 ADB 查看：
```bash
adb shell cat /data/data/com.musicdl/files/logs/music-dl.log
adb pull /data/data/com.musicdl/files/logs/music-dl.log ./
```

或在应用内通过 API 导出：
```
GET /api/logs/status
POST /api/logs/export {"format":"json"}
```

## 构建

```bash
cd android
# Windows
powershell -File build_full.ps1

# macOS/Linux
bash build_apk.sh
```

需要：JDK 17+, Android SDK 34, Python 3.12 (Chaquopy)

## 安全特性

- 网络安全配置：仅 localhost HTTP 明文
- `allowBackup=false`
- WebView `setAllowFileAccess(false)`
- R8 混淆 + 资源压缩
- StrictMode (debug)
- 音频焦点管理 + 耳机拔出检测

## 版本

基于主线 v1.4.2，同步安全加固、音频增强、统一日志等特性。
