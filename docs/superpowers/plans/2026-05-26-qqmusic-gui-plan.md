# Streamlit GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Streamlit web GUI to the QQ Music downloader (single `app.py` file).

**Architecture:** `app.py` imports `api.py`, `downloader.py`, `models.py`, `utils.py` — no changes to existing files. Adds `streamlit` to requirements.txt.

**Tech Stack:** Python 3.14, streamlit, requests, rich (existing)

---

### Task 1: Install Streamlit and Write app.py

**Files:**
- Modify: `requirements.txt`
- Create: `app.py`

- [ ] **Step 1: Add streamlit to requirements.txt and install**

Add to requirements.txt:
```
streamlit>=1.28
```

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && pip3 install --break-system-packages streamlit
```

- [ ] **Step 2: Write app.py**

```python
"""Streamlit GUI for QQ Music Downloader."""
import streamlit as st
from pathlib import Path
from api import QQMusicAPI
from models import Song
from downloader import Downloader, print_summary
from utils import load_config, save_config, QUALITY_MAP

st.set_page_config(page_title="QQ Music Downloader", page_icon="🎵", layout="wide")

CONFIG_PATH = Path.home() / ".config" / "qqmusic-dl" / "config.json"

# ── Session state init ──
if "api" not in st.session_state:
    st.session_state.api = QQMusicAPI()
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

    quality = st.selectbox(
        "音质", list(QUALITY_MAP.keys()),
        index=list(QUALITY_MAP.keys()).index(config.get("quality", "320kbps")),
        format_func=lambda q: QUALITY_MAP[q]["desc"],
    )

    save_dir = st.text_input("下载目录", value=config.get("download_dir", str(Path.home() / "Music" / "QQMusic")))

    workers = st.slider("并发数", 1, 6, config.get("workers", 3))

    if st.button("💾 保存设置"):
        config["quality"] = quality
        config["download_dir"] = save_dir
        config["workers"] = workers
        save_config(CONFIG_PATH, config)
        st.success("设置已保存")

    st.markdown("---")
    st.metric("本次已下载", st.session_state.downloaded)

# ── Main area ──
st.title("QQ 音乐下载器")
st.caption("搜索歌曲 → 勾选 → 一键下载")

# Search row
col1, col2, col3 = st.columns([5, 1, 1])
with col1:
    keyword = st.text_input("搜索关键词", placeholder="输入歌曲名或歌手名...", label_visibility="collapsed")
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

if not st.session_state.songs and keyword.strip():
    st.info("输入关键词后点击搜索")

songs = st.session_state.songs

# Results table
if songs:
    st.markdown(f"### 搜索结果 ({len(songs)} 首)")

    # Select all
    all_checked = st.checkbox("全选", key="select_all")

    selected = []
    for i, song in enumerate(songs):
        cols = st.columns([0.05, 0.35, 0.25, 0.2, 0.15])
        with cols[0]:
            checked = st.checkbox("", key=f"song_{i}", value=all_checked)
        with cols[1]:
            gray_label = " ⛔" if song.is_gray else ""
            st.write(f"{song.title}{gray_label}")
        with cols[2]:
            st.write(song.singer)
        with cols[3]:
            st.write(song.album)
        with cols[4]:
            st.write(song.duration_str)

        if checked:
            selected.append(song)

    st.markdown("---")

    # Download button
    dl_col1, dl_col2 = st.columns([1, 3])
    with dl_col1:
        if st.button(f"⬇ 下载选中 ({len(selected)} 首)", type="primary", use_container_width=True,
                     disabled=len(selected) == 0):
            dl = Downloader(api, save_dir, quality=quality, workers=workers)
            progress_bar = st.progress(0, text="准备下载...")
            status_area = st.empty()

            total = len(selected)
            succeeded = 0
            failed = 0
            skipped = 0

            for idx, song in enumerate(selected):
                progress_bar.progress((idx) / total, text=f"下载中: {song.title} - {song.singer}")
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
            st.info(f"文件保存在: {save_dir}")
```

- [ ] **Step 3: Verify it imports**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && python3 -c "import streamlit; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Launch and test**

```bash
cd /Users/boqing/Desktop/code/qqmusic-dl && streamlit run app.py
```

Open http://localhost:8501, search for a song, select, download. Verify:
1. Search returns results in the table
2. Checkboxes work (individual + select all)
3. Download button triggers download
4. Progress bar updates
5. Sidebar settings persist
6. Download counter increments

- [ ] **Step 5: Stop the server (Ctrl+C)**
