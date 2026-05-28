"""Streamlit GUI for QQ Music Downloader."""
import streamlit as st
from pathlib import Path
from api import QQMusicAPI
from models import Song
from downloader import Downloader
from utils import load_config, save_config, QUALITY_MAP

st.set_page_config(page_title="QQ Music Downloader", page_icon="🎵", layout="wide")

CONFIG_PATH = Path.home() / ".config" / "qqmusic-dl" / "config.json"

# ── Session state init ──
if "api" not in st.session_state:
    config_init = load_config(CONFIG_PATH)
    cookie = config_init.get("cookie", "")
    st.session_state.api = QQMusicAPI(cookie_str=cookie)
if "songs" not in st.session_state:
    st.session_state.songs = []
if "downloaded" not in st.session_state:
    st.session_state.downloaded = 0

api = st.session_state.api

# ── Sidebar ──
with st.sidebar:
    st.title("🎵 QQ 音乐下载器")
    st.markdown("---")

    config = load_config(CONFIG_PATH)

    # Cookie / Login section
    with st.expander("🔑 登录", expanded=not bool(config.get("cookie", ""))):
        st.caption("自动从 Chrome 提取 Cookie（包括 HttpOnly）")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🚀 打开登录窗口", use_container_width=True):
                import subprocess
                subprocess.Popen([
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "--remote-debugging-port=9233",
                    "--remote-allow-origins=*",
                    "--user-data-dir=/tmp/chrome-cdp-v3",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "https://y.qq.com",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                st.success("Chrome 已打开 → 微信扫码登录")
        with col_b:
            if st.button("🔍 一键提取 Cookie", use_container_width=True, type="primary"):
                from cdp_cookies import get_cookies_via_ws
                with st.spinner("正在从 Chrome 提取..."):
                    cookie = get_cookies_via_ws()
                if cookie:
                    config["cookie"] = cookie
                    save_config(CONFIG_PATH, config)
                    if api.set_cookie(cookie):
                        st.success("✅ 已登录！Cookie 已保存")
                        st.rerun()
                    else:
                        st.warning("Cookie 提取了但格式异常，请确认已登录")
                else:
                    st.error("提取失败。请先点「打开登录窗口」→ 微信扫码 → 再点提取")

        st.caption("① 打开登录窗口 → ② 微信扫码 → ③ 一键提取 Cookie")

        st.divider()
        with st.expander("📋 手动输入（备用）"):
            col1, col2 = st.columns(2)
            with col1:
                uin_input = st.text_input("uin / wxuin", placeholder="QQ号")
            with col2:
                key_input = st.text_input("qqmusic_key / qm_keyst", placeholder="Key", type="password")
            if st.button("✅ 手动登录"):
                uin_val = uin_input.strip()
                key_val = key_input.strip()
                if uin_val and key_val:
                    cookie_str = f"uin={uin_val}; qqmusic_key={key_val}"
                    if api.set_cookie(cookie_str):
                        config["cookie"] = cookie_str
                        save_config(CONFIG_PATH, config)
                        st.success("登录成功")
                        st.rerun()
            if st.button("🧹 清除"):
                config["cookie"] = ""
                save_config(CONFIG_PATH, config)
                st.session_state.api = QQMusicAPI()
                st.rerun()

        if api.g_tk:
            st.success("✅ 已登录")
        else:
            st.info("ℹ 未登录")

    quality = st.selectbox(
        "音质", list(QUALITY_MAP.keys()),
        index=list(QUALITY_MAP.keys()).index(config.get("quality", "320kbps")),
        format_func=lambda q: QUALITY_MAP[q]["desc"],
    )

    multi_source = st.checkbox("🔀 多音源回退（VIP歌曲自动换源）", value=True,
        help="QQ音乐VIP歌曲自动搜索网易云等免费音源替代")

    save_dir = st.text_input(
        "下载目录",
        value=config.get("download_dir", str(Path.home() / "Music" / "QQMusic")),
    )

    workers = st.slider("并发数", 1, 6, config.get("workers", 3))

    if st.button("💾 保存设置"):
        config["quality"] = quality
        config["download_dir"] = save_dir
        config["workers"] = workers
        save_config(CONFIG_PATH, config)
        st.success("设置已保存")

    st.markdown("---")
    st.metric("本次已下载", st.session_state.downloaded)

    # AI source discovery
    with st.expander("🤖 AI 发现音源", expanded=False):
        st.caption("搜索互联网 + AI 分析 → 自动注册新音源")

        # AI model selection
        ai_model = st.selectbox(
            "AI 分析引擎",
            [
                "rule-based (免费，无需Key)",
                "openai (gpt-4o-mini)",
                "openai (custom model)",
                "claude (haiku)",
            ],
        )

        # Only show API config when not rule-based
        ai_base_url = ""
        ai_key = ""
        if "rule-based" not in ai_model:
            st.markdown("**API 配置**")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                default_url = "https://api.anthropic.com" if "claude" in ai_model else "https://api.openai.com"
                ai_base_url = st.text_input(
                    "Base URL",
                    placeholder=default_url,
                    value=default_url,
                )
            with col_b2:
                ai_key = st.text_input(
                    "API Key",
                    placeholder="sk-..." if "openai" in ai_model else "sk-ant-...",
                    type="password",
                )

        if st.button("🔍 开始搜索音源", use_container_width=True):
            # Determine AI config
            ai_api = ""
            model = ""
            base_url = ai_base_url.strip()

            if ai_key.strip() and "openai" in ai_model:
                ai_api = "openai"
                model = "gpt-4o-mini" if "4o-mini" in ai_model else ""
                if not base_url:
                    base_url = "https://api.openai.com"
            elif ai_key.strip() and "claude" in ai_model:
                ai_api = "claude"
                if not base_url:
                    base_url = "https://api.anthropic.com"

            with st.spinner("Phase 1: 探测已知API → Phase 2: 搜索网页 → Phase 3: 逐页AI分析..."):
                try:
                    import sources
                    from sources.ai_discovery import discover_pipeline

                    progress_msgs = []
                    def on_progress(msg):
                        progress_msgs.append(msg)
                        if len(progress_msgs) > 8:
                            progress_msgs.pop(0)

                    discovered = discover_pipeline(
                        progress_callback=on_progress,
                        ai_api=ai_api,
                        ai_key=ai_key.strip(),
                        base_url=base_url,
                        ai_model=model,
                        max_pages=15,
                    )
                    if discovered:
                        st.success(f"✅ 发现 {len(discovered)} 个新音源！")
                        for d in discovered:
                            conf = d.get('confidence', 0)
                            st.write(f"  🎵 {d['name']} (置信度 {conf:.0%}) — {d.get('url','')[:60]}")
                    else:
                        st.info("未发现新音源（已覆盖主流平台）")
                except Exception as e:
                    st.error(f"搜索失败: {e}")

        # Show current sources
        if st.button("📊 查看所有音源状态", use_container_width=True):
            with st.spinner("测试音源..."):
                import sources
                status = sources.test_all_sources()
                for name, info in status.items():
                    icon = "✅" if info.get("available") else "❌"
                    detail = f'{info.get("results", "?")} results' if info.get("available") else info.get("error", "?")
                    st.write(f"  {icon} {name}: {detail}")

# ── Main area ──
st.title("QQ 音乐下载器")
st.caption("搜索歌曲 → 勾选 → 一键下载")

# Search row
col1, col2, col3 = st.columns([5, 1, 1])
# Favorites button row
fav_col1, fav_col2 = st.columns([1, 8])
with fav_col1:
    if st.button("❤️ 我的收藏", use_container_width=True, help="获取你点过红心的歌曲"):
        if not api.g_tk:
            st.error("请先在侧边栏登录 (扫码或粘贴Cookie)")
        else:
            with st.spinner("获取收藏列表..."):
                fav_songs = api.get_fav_songs(page=0, size=200)
            if fav_songs:
                st.session_state.songs = fav_songs
                st.success(f"获取到 {len(fav_songs)} 首收藏歌曲")
                st.rerun()
            else:
                st.warning("获取失败，可能需要重新登录")

# Playlist URL row
pl_col1, pl_col2 = st.columns([6, 1])
with pl_col1:
    playlist_url = st.text_input(
        "歌单链接",
        placeholder="粘贴 QQ 音乐歌单链接... 例如 https://y.qq.com/n/ryqq/playlist/123456",
        label_visibility="collapsed",
    )
with pl_col2:
    if st.button("📋 获取歌单", use_container_width=True, disabled=not playlist_url.strip()):
        try:
            pid = QQMusicAPI.extract_playlist_id(playlist_url.strip())
        except ValueError:
            st.error("无法识别歌单链接")
            pid = None
        if pid:
            with st.spinner(f"正在加载歌单 {pid}..."):
                songs = QQMusicAPI.extract_playlist_from_html(pid)
            if songs:
                st.session_state.songs = songs
                st.success(f"获取到 {len(songs)} 首歌（通过浏览器提取）")
                st.rerun()
            else:
                st.error("加载失败。请确认：① CDP Chrome 在运行 ② 已登录 y.qq.com")

# Search row
with col1:
    keyword = st.text_input(
        "搜索关键词", placeholder="输入歌曲名或歌手名...",
        label_visibility="collapsed",
    )
with col2:
    limit = st.selectbox("条数", [5, 10, 20, 30], index=1, label_visibility="collapsed")
with col3:
    search_btn = st.button("🔍 搜索", use_container_width=True)

if search_btn and keyword.strip():
    with st.spinner(f"搜索 '{keyword}' ..."):
        try:
            st.session_state.songs = api.search(keyword.strip(), limit=limit)
        except Exception as e:
            st.error(f"搜索失败: {e}")
            st.session_state.songs = []

if not st.session_state.songs and not search_btn:
    st.info("👆 输入关键词后点击搜索")

songs = st.session_state.songs

# Results table
if songs:
    st.markdown(f"### 搜索结果 ({len(songs)} 首)")

    # Song list with multiselect for reliable select/deselect
    song_labels = []
    song_map = {}
    for i, song in enumerate(songs):
        gray = " ⛔" if song.is_gray else ""
        label = f"{song.title}{gray}  |  {song.singer}  |  {song.album}  |  {song.duration_str}"
        song_labels.append(label)
        song_map[label] = song

    # All/none buttons
    c1, c2, c3 = st.columns([1, 1, 5])
    with c1:
        if st.button("☑ 全选", use_container_width=True):
            st.session_state.selected_labels = song_labels[:]
            st.rerun()
    with c2:
        if st.button("☐ 取消", use_container_width=True):
            st.session_state.selected_labels = []
            st.rerun()

    if "selected_labels" not in st.session_state:
        st.session_state.selected_labels = []

    chosen = st.multiselect(
        f"共 {len(songs)} 首，勾选要下载的歌曲",
        options=song_labels,
        default=st.session_state.selected_labels,
        key="song_selector",
        label_visibility="collapsed",
    )
    st.session_state.selected_labels = chosen

    selected = [song_map[label] for label in chosen]

    st.markdown("---")

    # Download button
    dl_col1, dl_col2 = st.columns([1, 3])
    with dl_col1:
        disabled = len(selected) == 0
        if st.button(
            f"⬇ 下载选中 ({len(selected)} 首)",
            type="primary",
            use_container_width=True,
            disabled=disabled,
        ):
            dl = Downloader(api, save_dir, quality=quality, workers=workers)
            progress_bar = st.progress(0, text="准备下载...")

            total = len(selected)
            succeeded = 0
            failed = 0
            skipped = 0

            for idx, song in enumerate(selected):
                progress_bar.progress(
                    idx / total, text=f"下载中: {song.title} - {song.singer}"
                )
                ok = dl.download(song)
                if ok:
                    succeeded += 1
                elif song.is_gray:
                    skipped += 1
                else:
                    failed += 1

            progress_bar.progress(1.0, text="完成!")
            st.session_state.downloaded += succeeded

            if succeeded:
                st.success(f"✅ 成功: {succeeded} 首")
            if failed:
                st.error(f"❌ 失败: {failed} 首")
            if skipped:
                st.warning(f"⏭ 跳过: {skipped} 首")
            st.info(f"📁 文件保存在: {save_dir}")
