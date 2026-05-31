package com.musicdl;

import android.Manifest;
import android.content.pm.PackageManager;
import android.media.MediaPlayer;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.*;
import java.util.concurrent.*;

public class MainActivity extends AppCompatActivity {
    private static final String TAG = "MusicDL";
    private static final String API = "http://127.0.0.1:8765";
    private static final ExecutorService serverExecutor = Executors.newSingleThreadExecutor();
    private static final ExecutorService apiExecutor = Executors.newCachedThreadPool();
    private static final Handler mainHandler = new Handler(Looper.getMainLooper());

    private LinearLayout mainLayout, resultList, miniPlayer, downloadList;
    private EditText searchInput;
    private ProgressBar progressBar;
    private TextView playerTitle, playerArtist, statusText;
    private Button playPauseBtn;
    private MediaPlayer mediaPlayer;
    private String currentPlayUrl;
    private JSONArray currentSongs = new JSONArray();
    private Set<Integer> selected = new HashSet<>();
    private String quality = "320kbps";
    private String preferSource = "auto";
    private String currentPlatform = "qq";

    private static final String[] PLATFORM_URLS = {
        "https://y.qq.com", "https://music.163.com", "https://www.kugou.com"
    };
    private static final String[] PLATFORM_DOMAINS = {"y.qq.com", "music.163.com", "kugou.com"};
    private static final String[] PLATFORM_NAMES = {"QQ", "网易云", "酷狗"};
    private static final String[] PLATFORM_KEYS = {"qq", "netease", "kugou"};

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Start Python server (separate thread, never blocks API calls)
        serverExecutor.execute(() -> {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
            Python.getInstance().getModule("server_runner").callAttr("run_server");
        });

        // Wait for server then init UI
        mainHandler.postDelayed(this::initUI, 3000);
    }

    private void initUI() {
        mainLayout = new LinearLayout(this);
        mainLayout.setOrientation(LinearLayout.VERTICAL);
        mainLayout.setBackgroundColor(0xFF0a0a0f);
        mainLayout.setPadding(16, 40, 16, 16);

        // Title
        TextView title = new TextView(this);
        title.setText("Music DL");
        title.setTextColor(0xFFe8e8ed);
        title.setTextSize(22);
        title.setTypeface(null, Typeface.BOLD);
        title.setPadding(0, 0, 0, 12);
        mainLayout.addView(title);

        // Status
        statusText = new TextView(this);
        statusText.setText("● 启动中...");
        statusText.setTextColor(0xFFf59e0b);
        statusText.setTextSize(13);
        statusText.setPadding(0, 0, 0, 8);
        mainLayout.addView(statusText);

        // Search bar
        LinearLayout searchBar = new LinearLayout(this);
        searchBar.setOrientation(LinearLayout.HORIZONTAL);
        searchInput = new EditText(this);
        searchInput.setHint("搜索歌曲、歌手...");
        searchInput.setHintTextColor(0xFF6b6f80);
        searchInput.setTextColor(0xFFe8e8ed);
        searchInput.setBackground(roundedBg(0xFF1a1d28, 28));
        searchInput.setPadding(40, 28, 20, 28);
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        sp.setMargins(0, 0, 8, 0);
        searchInput.setLayoutParams(sp);
        searchInput.addTextChangedListener(new TextWatcher() {
            public void afterTextChanged(Editable s) { doSearch(s.toString()); }
            public void beforeTextChanged(CharSequence s, int st, int c, int a) {}
            public void onTextChanged(CharSequence s, int st, int b, int c) {}
        });
        searchBar.addView(searchInput);

        Button loginBtn = new Button(this);
        loginBtn.setText("🔑");
        loginBtn.setTextColor(0xFFe8e8ed);
        loginBtn.setBackground(roundedBg(0xFF1a1d28, 28));
        loginBtn.setOnClickListener(v -> showLoginDialog());
        searchBar.addView(loginBtn);
        mainLayout.addView(searchBar);

        // Source chips
        LinearLayout chips = new LinearLayout(this);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        String[] sources = {"自动", "QQ", "网易云", "酷狗", "GitHub", "网页"};
        String[] srcKeys = {"auto", "qq", "netease", "kugou", "github", "web"};
        for (int i = 0; i < sources.length; i++) {
            Button chip = new Button(this);
            chip.setText(sources[i]);
            chip.setTextSize(11);
            chip.setPadding(20, 10, 20, 10);
            chip.setBackground(roundedBg(i == 0 ? 0xFF8b5cf6 : 0x001a1d28, 20));
            chip.setTextColor(i == 0 ? 0xFFFFFFFF : 0xFF6b6f80);
            int idx = i;
            chip.setOnClickListener(v -> {
                preferSource = srcKeys[idx];
                for (int j = 0; j < chips.getChildCount(); j++) {
                    Button c = (Button) chips.getChildAt(j);
                    c.setBackground(roundedBg(j == idx ? 0xFF8b5cf6 : 0x001a1d28, 20));
                    c.setTextColor(j == idx ? 0xFFFFFFFF : 0xFF6b6f80);
                }
                doSearch(searchInput.getText().toString());
            });
            LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            cp.setMargins(0, 0, 8, 0);
            chip.setLayoutParams(cp);
            chips.addView(chip);
        }
        mainLayout.addView(chips);

        // Progress
        progressBar = new ProgressBar(this);
        progressBar.setIndeterminate(true);
        progressBar.setVisibility(View.GONE);
        mainLayout.addView(progressBar);

        // Result list
        resultList = new LinearLayout(this);
        resultList.setOrientation(LinearLayout.VERTICAL);
        mainLayout.addView(resultList);

        // Mini player
        miniPlayer = new LinearLayout(this);
        miniPlayer.setOrientation(LinearLayout.HORIZONTAL);
        miniPlayer.setBackgroundColor(0xFF12141c);
        miniPlayer.setPadding(16, 12, 16, 12);
        miniPlayer.setVisibility(View.GONE);

        playPauseBtn = new Button(this);
        playPauseBtn.setText("▶");
        playPauseBtn.setTextColor(0xFFe8e8ed);
        playPauseBtn.setBackground(roundedBg(0xFF8b5cf6, 24));
        playPauseBtn.setPadding(20, 10, 20, 10);
        playPauseBtn.setOnClickListener(v -> togglePlay());
        miniPlayer.addView(playPauseBtn);

        LinearLayout info = new LinearLayout(this);
        info.setOrientation(LinearLayout.VERTICAL);
        info.setPadding(12, 0, 0, 0);
        playerTitle = new TextView(this);
        playerTitle.setTextColor(0xFFe8e8ed);
        playerTitle.setTextSize(14);
        playerTitle.setTypeface(null, Typeface.BOLD);
        info.addView(playerTitle);
        playerArtist = new TextView(this);
        playerArtist.setTextColor(0xFF6b6f80);
        playerArtist.setTextSize(12);
        info.addView(playerArtist);
        miniPlayer.addView(info);

        Button stopBtn = new Button(this);
        stopBtn.setText("✕");
        stopBtn.setTextColor(0xFF6b6f80);
        stopBtn.setBackgroundColor(0x00000000);
        stopBtn.setOnClickListener(v -> stopPlay());
        miniPlayer.addView(stopBtn);
        mainLayout.addView(miniPlayer);

        // Bottom nav
        LinearLayout nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setBackgroundColor(0xFF12141c);
        nav.setPadding(0, 12, 0, 24);
        String[] tabs = {"🔍 搜索", "📥 下载", "⚙ 设置"};
        for (int i = 0; i < tabs.length; i++) {
            Button tab = new Button(this);
            tab.setText(tabs[i]);
            tab.setTextColor(0xFF6b6f80);
            tab.setTextSize(13);
            tab.setBackgroundColor(0x00000000);
            LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
            tab.setLayoutParams(tp);
            int idx = i;
            tab.setOnClickListener(v -> {
                if (idx == 1) showDownloads();
                if (idx == 2) showSettings();
                if (idx == 0) { resultList.setVisibility(View.VISIBLE); if (downloadList != null) downloadList.setVisibility(View.GONE); }
            });
            nav.addView(tab);
        }
        mainLayout.addView(nav);

        setContentView(mainLayout);

        // Check server
        mainHandler.postDelayed(this::checkServer, 5000);
    }

    private void checkServer() {
        apiGet("/api/status", new Callback() {
            public void onResult(JSONObject r) {
                boolean loggedIn = r.optBoolean("logged_in");
                String uin = r.optString("uin", "");
                mainHandler.post(() -> {
                    statusText.setText(loggedIn ? "● 已登录" + (uin.isEmpty() ? "" : " uin:" + uin) : "● 未登录");
                    statusText.setTextColor(loggedIn ? 0xFF10b981 : 0xFFef4444);
                });
            }
            public void onError(String e) {}
        });
    }

    private void doSearch(String kw) {
        if (kw.trim().isEmpty()) { resultList.removeAllViews(); return; }
        progressBar.setVisibility(View.VISIBLE);
        resultList.removeAllViews();
        apiPost("/api/search", "{\"keyword\":\"" + escape(kw) + "\",\"limit\":20}", new Callback() {
            public void onResult(JSONObject r) {
                JSONArray songs = r.optJSONArray("songs");
                currentSongs = songs != null ? songs : new JSONArray();
                mainHandler.post(() -> {
                    progressBar.setVisibility(View.GONE);
                    resultList.removeAllViews();
                    for (int i = 0; i < currentSongs.length(); i++) {
                        try {
                            JSONObject s = currentSongs.getJSONObject(i);
                            resultList.addView(createSongCard(s, i));
                        } catch (Exception e) {}
                    }
                    if (currentSongs.length() == 0) {
                        TextView empty = new TextView(MainActivity.this);
                        empty.setText("🎵\n未找到歌曲");
                        empty.setTextColor(0xFF6b6f80);
                        empty.setTextSize(14);
                        empty.setTextAlignment(View.TEXT_ALIGNMENT_CENTER);
                        empty.setPadding(0, 60, 0, 0);
                        resultList.addView(empty);
                    }
                });
            }
            public void onError(String e) {
                mainHandler.post(() -> progressBar.setVisibility(View.GONE));
            }
        });
    }

    private View createSongCard(JSONObject s, int i) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setBackground(roundedBg(0xFF12141c, 16));
        card.setPadding(12, 12, 12, 12);
        LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        cp.setMargins(0, 0, 0, 8);
        card.setLayoutParams(cp);

        // Play button
        Button playBtn = new Button(this);
        playBtn.setText("▶");
        playBtn.setTextColor(0xFFa78bfa);
        playBtn.setTextSize(12);
        playBtn.setBackground(roundedBg(0x201a1d28, 24));
        playBtn.setPadding(16, 8, 16, 8);
        String mid = s.optString("qqmid", s.optString("mid"));
        String title = s.optString("title");
        String singer = s.optString("singer");
        playBtn.setOnClickListener(v -> playSong(mid, title, singer));
        card.addView(playBtn);

        // Info
        LinearLayout info = new LinearLayout(this);
        info.setOrientation(LinearLayout.VERTICAL);
        info.setPadding(12, 0, 0, 0);
        TextView tv = new TextView(this);
        tv.setText(title);
        tv.setTextColor(0xFFe8e8ed);
        tv.setTextSize(15);
        tv.setTypeface(null, Typeface.BOLD);
        info.addView(tv);
        TextView sv = new TextView(this);
        sv.setText(singer + " · " + s.optString("duration_str"));
        sv.setTextColor(0xFF6b6f80);
        sv.setTextSize(12);
        info.addView(sv);

        // Source badges
        JSONArray sources = s.optJSONArray("sources");
        if (sources == null) { sources = new JSONArray(); sources.put(s.optString("source", "qq")); }
        LinearLayout badges = new LinearLayout(this);
        badges.setOrientation(LinearLayout.HORIZONTAL);
        for (int j = 0; j < sources.length(); j++) {
            String src = sources.optString(j);
            TextView badge = new TextView(this);
            badge.setText(src);
            badge.setTextSize(10);
            badge.setTextColor(0xFFFFFFFF);
            badge.setPadding(8, 3, 8, 3);
            int color = src.equals("qq") ? 0xFF8b5cf6 : src.equals("netease") ? 0xFFef4444 : src.equals("kugou") ? 0xFF3b82f6 : 0xFF333333;
            badge.setBackground(roundedBg(color, 4));
            LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            bp.setMargins(0, 4, 4, 0);
            badge.setLayoutParams(bp);
            badges.addView(badge);
        }
        info.addView(badges);
        card.addView(info);

        return card;
    }

    private void playSong(String mid, String title, String singer) {
        playerTitle.setText(title);
        playerArtist.setText(singer);
        miniPlayer.setVisibility(View.VISIBLE);
        playPauseBtn.setText("⏳");
        apiPost("/api/play", "{\"mid\":\"" + escape(mid) + "\",\"quality\":\"" + quality + "\"}", new Callback() {
            public void onResult(JSONObject r) {
                String url = r.optString("url", "");
                if (url.isEmpty()) { mainHandler.post(() -> toast("无法获取播放链接")); return; }
                if (!url.startsWith("http")) { mainHandler.post(() -> toast("无效链接:" + url.substring(0,30))); return; }
                currentPlayUrl = url;
                mainHandler.post(() -> toast("下载中..."));
                // Download via cache, then play local file (MediaPlayer needs local file)
                apiGet("/api/cache?url=" + encode(url), new Callback() {
                    public void onResult(JSONObject cr) {
                        String path = cr.optString("path", "");
                        if (!path.isEmpty()) {
                            mainHandler.post(() -> playFile(path));
                        } else {
                            mainHandler.post(() -> toast("下载失败"));
                        }
                    }
                    public void onError(String e) { mainHandler.post(() -> toast("缓存失败: " + e)); }
                });
            }
            public void onError(String e) { mainHandler.post(() -> toast("播放失败: " + (e != null ? e : "unknown"))); }
        });
    }

    private void playUrl(String url) {
        try {
            if (mediaPlayer != null) { mediaPlayer.release(); }
            mediaPlayer = new MediaPlayer();
            mediaPlayer.setAudioStreamType(android.media.AudioManager.STREAM_MUSIC);
            mediaPlayer.setDataSource(url);
            mediaPlayer.setVolume(1.0f, 1.0f);
            mediaPlayer.setOnPreparedListener(mp -> {
                mp.start();
                playPauseBtn.setText("⏸");
                toast("正在播放");
            });
            mediaPlayer.setOnCompletionListener(mp -> playPauseBtn.setText("▶"));
            mediaPlayer.setOnErrorListener((mp, w, e) -> { toast("错误:" + w + "/" + e); return true; });
            mediaPlayer.setOnInfoListener((mp, what, extra) -> {
                if (what == MediaPlayer.MEDIA_INFO_BUFFERING_START) toast("缓冲中...");
                if (what == MediaPlayer.MEDIA_INFO_BUFFERING_END) toast("缓冲完成");
                if (what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) toast("开始渲染");
                return false;
            });
            mediaPlayer.prepareAsync();
        } catch (Exception ex) {
            toast("播放异常: " + ex.getClass().getSimpleName() + " " + (ex.getMessage() != null ? ex.getMessage() : ""));
        }
    }

    private void playFile(String path) {
        try {
            java.io.File f = new java.io.File(path);
            if (!f.exists()) { toast("文件不存在:" + path); return; }
            if (mediaPlayer != null) { mediaPlayer.release(); }
            mediaPlayer = new MediaPlayer();
            mediaPlayer.setDataSource(path);
            mediaPlayer.setOnPreparedListener(mp -> {
                mp.start();
                playPauseBtn.setText("⏸");
            });
            mediaPlayer.setOnCompletionListener(mp -> playPauseBtn.setText("▶"));
            mediaPlayer.setOnErrorListener((mp, w, e) -> { toast("错误:" + w + "/" + e); return true; });
            mediaPlayer.prepareAsync();
        } catch (Exception e) {
            toast("播放失败: " + e.getMessage());
        }
    }

    private void togglePlay() {
        if (mediaPlayer == null) return;
        try {
            if (mediaPlayer.isPlaying()) { mediaPlayer.pause(); playPauseBtn.setText("▶"); }
            else { mediaPlayer.start(); playPauseBtn.setText("⏸"); }
        } catch (Exception e) {}
    }

    private void stopPlay() {
        if (mediaPlayer != null) { try { mediaPlayer.stop(); mediaPlayer.release(); } catch (Exception e) {} mediaPlayer = null; }
        miniPlayer.setVisibility(View.GONE);
    }

    private void showLoginDialog() {
        // Remove any existing overlay first
        View existing = findViewById(9999);
        if (existing != null) ((ViewGroup) existing.getParent()).removeView(existing);

        // Dark overlay that dismisses on tap
        FrameLayout overlay = new FrameLayout(this);
        overlay.setId(9999);
        overlay.setBackgroundColor(0x99000000);
        overlay.setOnClickListener(v -> ((ViewGroup) overlay.getParent()).removeView(overlay));
        overlay.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        // Sheet
        LinearLayout sheet = new LinearLayout(this);
        sheet.setOrientation(LinearLayout.VERTICAL);
        sheet.setBackgroundColor(0xFF12141c);
        sheet.setPadding(32, 32, 32, 32);
        FrameLayout.LayoutParams sp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        sp.gravity = android.view.Gravity.BOTTOM;
        sheet.setLayoutParams(sp);
        sheet.setOnClickListener(v -> {}); // don't dismiss when tapping sheet

        TextView sh = new TextView(this);
        sh.setText("登录");
        sh.setTextColor(0xFFe8e8ed);
        sh.setTextSize(18);
        sh.setTypeface(null, Typeface.BOLD);
        sh.setPadding(0, 0, 0, 16);
        sheet.addView(sh);

        // Platform tabs
        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setPadding(0, 0, 0, 12);
        for (int i = 0; i < PLATFORM_NAMES.length; i++) {
            Button tab = new Button(this);
            tab.setText(PLATFORM_NAMES[i]);
            tab.setTextColor(i == 0 ? 0xFFFFFFFF : 0xFF6b6f80);
            tab.setBackground(roundedBg(i == 0 ? 0xFF8b5cf6 : 0x001a1d28, 8));
            tab.setTextSize(13);
            tab.setPadding(20, 10, 20, 10);
            int idx = i;
            tab.setOnClickListener(v -> {
                currentPlatform = PLATFORM_KEYS[idx];
                for (int j = 0; j < tabs.getChildCount(); j++) {
                    Button c = (Button) tabs.getChildAt(j);
                    c.setBackground(roundedBg(j == idx ? 0xFF8b5cf6 : 0x001a1d28, 8));
                    c.setTextColor(j == idx ? 0xFFFFFFFF : 0xFF6b6f80);
                }
            });
            LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
            tp.setMargins(0, 0, 4, 0);
            tab.setLayoutParams(tp);
            tabs.addView(tab);
        }
        sheet.addView(tabs);

        LinearLayout btns = new LinearLayout(this);
        btns.setOrientation(LinearLayout.HORIZONTAL);
        Button openBtn = new Button(this);
        openBtn.setText("打开登录页");
        openBtn.setTextColor(0xFFFFFFFF);
        openBtn.setBackground(roundedBg(0xFF8b5cf6, 8));
        openBtn.setPadding(20, 12, 20, 12);
        openBtn.setOnClickListener(v -> showLoginWebView(overlay));
        btns.addView(openBtn);

        Button extractBtn = new Button(this);
        extractBtn.setText("提取Cookie");
        extractBtn.setTextColor(0xFFFFFFFF);
        extractBtn.setBackground(roundedBg(0xFF10b981, 8));
        extractBtn.setPadding(20, 12, 20, 12);
        extractBtn.setOnClickListener(v -> extractCookie());
        LinearLayout.LayoutParams ep = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        ep.setMargins(8, 0, 0, 0);
        extractBtn.setLayoutParams(ep);
        btns.addView(extractBtn);
        sheet.addView(btns);

        Button closeBtn = new Button(this);
        closeBtn.setText("关闭");
        closeBtn.setTextColor(0xFF6b6f80);
        closeBtn.setBackgroundColor(0x00000000);
        closeBtn.setOnClickListener(v -> ((ViewGroup) overlay.getParent()).removeView(overlay));
        sheet.addView(closeBtn);

        overlay.addView(sheet);
        mainLayout.addView(overlay, 0);
    }

    private void showLoginWebView(FrameLayout overlay) {
        LinearLayout webContainer = new LinearLayout(this);
        webContainer.setOrientation(LinearLayout.VERTICAL);
        webContainer.setBackgroundColor(0xFF0a0a0f);
        FrameLayout.LayoutParams wp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        wp.setMargins(16, 60, 16, 60);
        webContainer.setLayoutParams(wp);

        WebView wv = new WebView(this);
        wv.getSettings().setJavaScriptEnabled(true);
        wv.getSettings().setDomStorageEnabled(true);
        wv.getSettings().setUserAgentString("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36");
        wv.setWebViewClient(new WebViewClient());
        CookieManager.getInstance().setAcceptCookie(true);
        LinearLayout.LayoutParams wvp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1);
        wv.setLayoutParams(wvp);
        webContainer.addView(wv);

        Button backBtn = new Button(this);
        backBtn.setText("← 返回登录页");
        backBtn.setTextColor(0xFF8b5cf6);
        backBtn.setBackgroundColor(0x00000000);
        backBtn.setOnClickListener(v -> { overlay.removeView(webContainer); toast("登录后点提取Cookie"); });
        webContainer.addView(backBtn);

        String[] urls = {"https://y.qq.com", "https://music.163.com", "https://www.kugou.com"};
        int idx = java.util.Arrays.asList(PLATFORM_KEYS).indexOf(currentPlatform);
        wv.loadUrl(urls[Math.max(0, idx)]);
        overlay.addView(webContainer);
    }

    private void extractCookie() {
        String domain = PLATFORM_DOMAINS[Math.max(0, java.util.Arrays.asList(PLATFORM_KEYS).indexOf(currentPlatform))];
        String cookie = CookieManager.getInstance().getCookie(domain);
        if (cookie == null || cookie.isEmpty()) { toast("未找到Cookie，请先登录"); return; }
        apiPost("/api/login/cookie?platform=" + currentPlatform,
            "{\"cookie\":\"" + escape(cookie) + "\",\"platform\":\"" + currentPlatform + "\"}", new Callback() {
            public void onResult(JSONObject r) {
                mainHandler.post(() -> { checkServer(); toast("Cookie已保存"); });
            }
            public void onError(String e) { mainHandler.post(() -> toast("保存失败")); }
        });
    }

    private void showDownloads() {
        if (downloadList != null) mainLayout.removeView(downloadList);
        downloadList = new LinearLayout(this);
        downloadList.setOrientation(LinearLayout.VERTICAL);
        resultList.setVisibility(View.GONE);
        mainLayout.addView(downloadList, mainLayout.indexOfChild(resultList));

        apiGet("/api/downloads", new Callback() {
            public void onResult(JSONObject r) {
                JSONArray files = r.optJSONArray("files");
                mainHandler.post(() -> {
                    downloadList.removeAllViews();
                    if (files == null || files.length() == 0) {
                        TextView empty = new TextView(MainActivity.this);
                        empty.setText("📥\n还没有下载任何歌曲");
                        empty.setTextColor(0xFF6b6f80);
                        empty.setTextSize(14);
                        empty.setTextAlignment(View.TEXT_ALIGNMENT_CENTER);
                        empty.setPadding(0, 60, 0, 0);
                        downloadList.addView(empty);
                        return;
                    }
                    for (int i = 0; i < files.length(); i++) {
                        try {
                            JSONObject f = files.getJSONObject(i);
                            LinearLayout row = new LinearLayout(MainActivity.this);
                            row.setOrientation(LinearLayout.HORIZONTAL);
                            row.setPadding(16, 12, 16, 12);
                            row.setBackground(roundedBg(0xFF12141c, 12));
                            LinearLayout.LayoutParams rp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                            rp.setMargins(0, 0, 0, 6);
                            row.setLayoutParams(rp);

                            Button pb = new Button(MainActivity.this);
                            pb.setText("▶");
                            pb.setTextColor(0xFFa78bfa);
                            pb.setBackground(roundedBg(0xFF8b5cf6, 24));
                            String path = f.optString("path");
                            pb.setOnClickListener(v -> playFile(path));
                            row.addView(pb);

                            LinearLayout ni = new LinearLayout(MainActivity.this);
                            ni.setOrientation(LinearLayout.VERTICAL);
                            ni.setPadding(12, 0, 0, 0);
                            TextView nt = new TextView(MainActivity.this);
                            nt.setText(f.optString("name"));
                            nt.setTextColor(0xFFe8e8ed);
                            nt.setTextSize(14);
                            ni.addView(nt);
                            TextView ns = new TextView(MainActivity.this);
                            ns.setText(String.format("%.1f MB", f.optLong("size") / 1048576.0));
                            ns.setTextColor(0xFF6b6f80);
                            ns.setTextSize(11);
                            ni.addView(ns);
                            row.addView(ni);
                            downloadList.addView(row);
                        } catch (Exception e) {}
                    }
                });
            }
            public void onError(String e) {}
        });
    }

    private void showSettings() {
        LinearLayout sheet = new LinearLayout(this);
        sheet.setOrientation(LinearLayout.VERTICAL);
        sheet.setBackgroundColor(0xFF12141c);
        sheet.setPadding(24, 24, 24, 24);

        TextView th = new TextView(this);
        th.setText("设置");
        th.setTextColor(0xFFe8e8ed);
        th.setTextSize(18);
        th.setTypeface(null, Typeface.BOLD);
        sheet.addView(th);

        String[] qs = {"128kbps", "320kbps", "flac"};
        for (String q : qs) {
            Button qb = new Button(this);
            qb.setText(q);
            qb.setTextColor(q.equals(quality) ? 0xFFFFFFFF : 0xFF6b6f80);
            qb.setBackground(roundedBg(q.equals(quality) ? 0xFF8b5cf6 : 0x001a1d28, 8));
            qb.setOnClickListener(v -> { quality = q; mainLayout.removeView(sheet); showSettings(); });
            sheet.addView(qb);
        }

        Button closeBtn = new Button(this);
        closeBtn.setText("关闭");
        closeBtn.setTextColor(0xFF6b6f80);
        closeBtn.setBackgroundColor(0x00000000);
        closeBtn.setOnClickListener(v -> mainLayout.removeView(sheet));
        sheet.addView(closeBtn);

        mainLayout.addView(sheet, 0);
    }

    // ── Helpers ──

    private void apiGet(String path, Callback cb) {
        apiExecutor.execute(() -> {
            try {
                URL u = new URL(API + path);
                HttpURLConnection c = (HttpURLConnection) u.openConnection();
                c.setRequestMethod("GET");
                c.setConnectTimeout(5000);
                c.setReadTimeout(15000);
                String resp = readStream(c.getInputStream());
                cb.onResult(new JSONObject(resp));
            } catch (Exception e) { cb.onError(e.getMessage()); }
        });
    }

    private void apiPost(String path, String body, Callback cb) {
        apiExecutor.execute(() -> {
            try {
                URL u = new URL(API + path);
                HttpURLConnection c = (HttpURLConnection) u.openConnection();
                c.setRequestMethod("POST");
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setConnectTimeout(5000);
                c.setReadTimeout(15000);
                c.getOutputStream().write(body.getBytes("UTF-8"));
                String resp = readStream(c.getInputStream());
                cb.onResult(new JSONObject(resp));
            } catch (Exception e) { cb.onError(e.getMessage()); }
        });
    }

    private String readStream(InputStream is) throws IOException {
        BufferedReader r = new BufferedReader(new InputStreamReader(is, "UTF-8"));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = r.readLine()) != null) sb.append(line);
        r.close();
        return sb.toString();
    }

    private String escape(String s) { return s.replace("\\", "\\\\").replace("\"", "\\\""); }
    private String encode(String s) { try { return URLEncoder.encode(s, "UTF-8"); } catch (Exception e) { return s; } }

    private GradientDrawable roundedBg(int color, int radius) {
        GradientDrawable gd = new GradientDrawable();
        gd.setColor(color);
        gd.setCornerRadius(dp(radius));
        return gd;
    }

    private int dp(int px) { return (int) (px * getResources().getDisplayMetrics().density); }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    interface Callback {
        void onResult(JSONObject r);
        void onError(String e);
    }
}
