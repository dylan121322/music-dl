package com.musicdl;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.StrictMode;
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
    private static final ExecutorService apiExecutor = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS, new LinkedBlockingQueue<>(16),
        new ThreadPoolExecutor.CallerRunsPolicy());
    private static final Handler mainHandler = new Handler(Looper.getMainLooper());

    private LinearLayout mainLayout, resultList, miniPlayer, downloadList;
    private EditText searchInput;
    private ProgressBar progressBar;
    private TextView playerTitle, playerArtist, statusText;
    private Button playPauseBtn;
    private MediaPlayer mediaPlayer;
    private Button retryBtn;
    private String currentMid, currentTitle, currentSinger;
    private String currentPlayUrl;
    private long cacheStartMs;
    private FrameLayout loginOverlay;
    private WebView loginWebView;
    private ViewGroup loginWebContainer;
    private JSONArray currentSongs = new JSONArray();
    private Set<Integer> selected = new HashSet<>();
    private String quality = "320kbps";
    private String preferSource = "auto";
    private String currentPlatform = "qq";
    private AudioManager audioManager;
    private AudioFocusRequest focusRequest;
    private boolean audioFocused = false;
    private BroadcastReceiver noisyReceiver;

    private static final String[] PLATFORM_URLS = {
        "https://y.qq.com", "https://music.163.com", "https://www.kugou.com"
    };
    private static final String[] PLATFORM_DOMAINS = {"y.qq.com", "music.163.com", "kugou.com"};
    private static final String[] PLATFORM_NAMES = {"QQ", "网易云", "酷狗"};
    private static final String[] PLATFORM_KEYS = {"qq", "netease", "kugou"};

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // StrictMode in debug builds
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            StrictMode.setThreadPolicy(new StrictMode.ThreadPolicy.Builder()
                .detectDiskReads().detectDiskWrites().detectNetwork()
                .penaltyLog().build());
            StrictMode.setVmPolicy(new StrictMode.VmPolicy.Builder()
                .detectLeakedSqlLiteObjects().detectLeakedClosableObjects()
                .penaltyLog().build());
        }

        setContentView(R.layout.activity_main);

        audioManager = (AudioManager) getSystemService(AUDIO_SERVICE);

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
        mainLayout.setBackgroundColor(0xFF000000);
        mainLayout.setPadding(20, 48, 20, 16);

        // Title row
        LinearLayout topRow = new LinearLayout(this);
        topRow.setOrientation(LinearLayout.HORIZONTAL);
        topRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        TextView title = new TextView(this);
        title.setText("Music DL");
        title.setTextColor(0xFFFFFFFF);
        title.setTextSize(26);
        title.setTypeface(Typeface.create("sans-serif-black", Typeface.BOLD));
        LinearLayout.LayoutParams titleLP = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        title.setLayoutParams(titleLP);
        topRow.addView(title);
        statusText = new TextView(this);
        statusText.setText("●");
        statusText.setTextColor(0xFFf59e0b);
        statusText.setTextSize(11);
        topRow.addView(statusText);
        mainLayout.addView(topRow);

        // Search bar — pill shaped with glass effect
        LinearLayout searchBar = new LinearLayout(this);
        searchBar.setOrientation(LinearLayout.HORIZONTAL);
        searchBar.setPadding(0, 16, 0, 12);
        searchInput = new EditText(this);
        searchInput.setHint("搜索歌曲、歌手...");
        searchInput.setHintTextColor(0xFF555555);
        searchInput.setTextColor(0xFFFFFFFF);
        searchInput.setTextSize(15);
        GradientDrawable pill = new GradientDrawable();
        pill.setColor(0xFF111111);
        pill.setCornerRadius(dp(30));
        pill.setStroke(dp(1), 0xFF222222);
        searchInput.setBackground(pill);
        searchInput.setPadding(dp(24), dp(16), dp(16), dp(16));
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        sp.setMargins(0, 0, dp(10), 0);
        searchInput.setLayoutParams(sp);
        searchInput.addTextChangedListener(new TextWatcher() {
            public void afterTextChanged(Editable s) { doSearch(s.toString()); }
            public void beforeTextChanged(CharSequence s, int st, int c, int a) {}
            public void onTextChanged(CharSequence s, int st, int b, int c) {}
        });
        searchBar.addView(searchInput);

        Button loginBtn = new Button(this);
        loginBtn.setText("🔑");
        loginBtn.setTextColor(0xFFFFFFFF);
        loginBtn.setTextSize(16);
        GradientDrawable loginBg = new GradientDrawable();
        loginBg.setColor(0xFF111111);
        loginBg.setCornerRadius(dp(30));
        loginBg.setStroke(dp(1), 0xFF222222);
        loginBtn.setBackground(loginBg);
        loginBtn.setPadding(dp(16), dp(12), dp(16), dp(12));
        loginBtn.setOnClickListener(v -> showLoginDialog());
        searchBar.addView(loginBtn);
        mainLayout.addView(searchBar);

        // Source chips — pill shaped, clean
        LinearLayout chips = new LinearLayout(this);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        chips.setPadding(0, 0, 0, dp(4));
        String[] sources = {"自动", "QQ", "网易云", "酷狗", "GitHub", "网页"};
        String[] srcKeys = {"auto", "qq", "netease", "kugou", "github", "web"};
        for (int i = 0; i < sources.length; i++) {
            Button chip = new Button(this);
            chip.setText(sources[i]);
            chip.setTextSize(11);
            chip.setPadding(dp(16), dp(8), dp(16), dp(8));
            GradientDrawable cbg = new GradientDrawable();
            cbg.setColor(i == 0 ? 0xFF8b5cf6 : 0x00000000);
            cbg.setCornerRadius(dp(16));
            if (i != 0) cbg.setStroke(dp(1), 0xFF222222);
            chip.setBackground(cbg);
            chip.setTextColor(i == 0 ? 0xFFFFFFFF : 0xFF777777);
            int idx = i;
            chip.setOnClickListener(v -> {
                preferSource = srcKeys[idx];
                for (int j = 0; j < chips.getChildCount(); j++) {
                    Button c = (Button) chips.getChildAt(j);
                    GradientDrawable g = new GradientDrawable();
                    g.setColor(j == idx ? 0xFF8b5cf6 : 0x00000000);
                    g.setCornerRadius(dp(16));
                    if (j != idx) g.setStroke(dp(1), 0xFF222222);
                    c.setBackground(g);
                    c.setTextColor(j == idx ? 0xFFFFFFFF : 0xFF777777);
                }
                doSearch(searchInput.getText().toString());
            });
            LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            cp.setMargins(0, 0, dp(8), 0);
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

        retryBtn = new Button(this);
        retryBtn.setText("重试");
        retryBtn.setTextColor(0xFFFFFFFF);
        retryBtn.setBackground(roundedBg(0xFFef4444, 24));
        retryBtn.setPadding(16, 10, 16, 10);
        retryBtn.setTextSize(12);
        retryBtn.setVisibility(View.GONE);
        retryBtn.setOnClickListener(v -> playSong(currentMid, currentTitle, currentSinger));
        miniPlayer.addView(retryBtn);

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
            LinearLayout.LayoutParams platLP = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
            platLP.setMargins(0, 0, 4, 0);
            tab.setLayoutParams(platLP);
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
        JSONObject body = new JSONObject();
        try { body.put("keyword", kw); body.put("limit", 20); } catch (Exception e) {}
        apiPost("/api/search", body.toString(), new Callback() {
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
        String primarySource = s.optString("source", "qq");
        int accentColor = primarySource.equals("netease") ? 0xFFef4444 : primarySource.equals("kugou") ? 0xFF3b82f6 : 0xFF8b5cf6;

        FrameLayout wrapper = new FrameLayout(this);
        LinearLayout.LayoutParams wp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        wp.setMargins(0, 0, 0, dp(10));
        wrapper.setLayoutParams(wp);

        // Card background with subtle gradient
        GradientDrawable cardBg = new GradientDrawable();
        cardBg.setColor(0xFF0a0a0a);
        cardBg.setCornerRadius(dp(16));
        cardBg.setStroke(dp(1), 0xFF1a1a1a);
        wrapper.setBackground(cardBg);

        // Left accent strip
        View accent = new View(this);
        accent.setBackgroundColor(accentColor);
        FrameLayout.LayoutParams ap = new FrameLayout.LayoutParams(dp(3), ViewGroup.LayoutParams.MATCH_PARENT);
        ap.gravity = android.view.Gravity.LEFT;
        GradientDrawable ag = new GradientDrawable();
        ag.setColor(accentColor);
        float[] corners = new float[]{dp(16), dp(16), 0, 0, 0, 0, dp(16), dp(16)};
        ag.setCornerRadii(corners);
        accent.setBackground(ag);
        wrapper.addView(accent);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setPadding(dp(16), dp(14), dp(14), dp(14));
        card.setGravity(android.view.Gravity.CENTER_VERTICAL);

        // Play button — large circle
        Button playBtn = new Button(this);
        playBtn.setText("▶");
        playBtn.setTextColor(0xFFFFFFFF);
        playBtn.setTextSize(14);
        GradientDrawable pb = new GradientDrawable();
        pb.setColor(accentColor);
        pb.setCornerRadius(dp(24));
        playBtn.setBackground(pb);
        playBtn.setPadding(dp(18), dp(12), dp(18), dp(12));
        String mid = s.optString("qqmid", s.optString("mid"));
        String title = s.optString("title");
        String singer = s.optString("singer");
        playBtn.setOnClickListener(v -> playSong(mid, title, singer));
        card.addView(playBtn);

        // Info
        LinearLayout info = new LinearLayout(this);
        info.setOrientation(LinearLayout.VERTICAL);
        info.setPadding(dp(14), 0, 0, 0);
        TextView tv = new TextView(this);
        tv.setText(title);
        tv.setTextColor(0xFFFFFFFF);
        tv.setTextSize(15);
        tv.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        tv.setMaxLines(1);
        tv.setEllipsize(android.text.TextUtils.TruncateAt.END);
        info.addView(tv);
        TextView sv = new TextView(this);
        sv.setText(singer + " · " + s.optString("duration_str"));
        sv.setTextColor(0xFF777777);
        sv.setTextSize(12);
        sv.setMaxLines(1);
        sv.setEllipsize(android.text.TextUtils.TruncateAt.END);
        info.addView(sv);

        // Source badges — micro pills
        JSONArray sources = s.optJSONArray("sources");
        if (sources == null) { sources = new JSONArray(); sources.put(primarySource); }
        LinearLayout badges = new LinearLayout(this);
        badges.setOrientation(LinearLayout.HORIZONTAL);
        for (int j = 0; j < sources.length(); j++) {
            String src = sources.optString(j);
            TextView badge = new TextView(this);
            badge.setText(src);
            badge.setTextSize(9);
            badge.setTextColor(src.equals("qq") ? 0xFFa78bfa : src.equals("netease") ? 0xFFf87171 : src.equals("kugou") ? 0xFF60a5fa : 0xFF777777);
            badge.setPadding(dp(6), dp(2), dp(6), dp(2));
            badge.setBackgroundColor(0x00000000);
            LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            bp.setMargins(0, dp(4), dp(4), 0);
            badge.setLayoutParams(bp);
            badges.addView(badge);
        }
        if (s.optBoolean("is_gray")) {
            TextView vip = new TextView(this);
            vip.setText("VIP");
            vip.setTextSize(9);
            vip.setTextColor(0xFFfbbf24);
            vip.setPadding(dp(6), dp(2), dp(6), dp(2));
            LinearLayout.LayoutParams vp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            vp.setMargins(0, dp(4), 0, 0);
            vip.setLayoutParams(vp);
            badges.addView(vip);
        }
        info.addView(badges);
        card.addView(info);

        wrapper.addView(card);
        return wrapper;
    }

    private void playSong(String mid, String title, String singer) {
        currentMid = mid;
        currentTitle = title;
        currentSinger = singer;
        retryBtn.setVisibility(View.GONE);

        playerTitle.setText(title);
        playerArtist.setText(singer);
        miniPlayer.setVisibility(View.VISIBLE);
        playPauseBtn.setText("⏳");

        JSONObject playBody = new JSONObject();
        try { playBody.put("mid", mid); playBody.put("quality", quality); } catch (Exception e) {}
        apiPost("/api/play", playBody.toString(), new Callback() {
            public void onResult(JSONObject r) {
                String url = r.optString("url", "");
                if (url.isEmpty()) { failAndRetry("无法获取播放链接"); return; }
                if (!url.startsWith("http")) { failAndRetry("无效链接"); return; }
                currentPlayUrl = url;

                // Start progress estimation for cache download
                cacheStartMs = System.currentTimeMillis();
                mainHandler.post(cacheProgressRunnable);

                apiGet("/api/cache?url=" + encode(url), new Callback() {
                    public void onResult(JSONObject cr) {
                        mainHandler.removeCallbacks(cacheProgressRunnable);
                        String path = cr.optString("path", "");
                        long size = cr.optLong("size", 0);
                        if (!path.isEmpty()) {
                            String sizeStr = size > 0 ? " (" + (size/1024) + "KB)" : "";
                            mainHandler.post(() -> { toast("缓存完成" + sizeStr); playFile(path); });
                        } else {
                            failAndRetry("下载失败: path为空");
                        }
                    }
                    public void onError(String e) {
                        mainHandler.removeCallbacks(cacheProgressRunnable);
                        failAndRetry("缓存失败: " + e);
                    }
                });
            }
            public void onError(String e) {
                failAndRetry("获取链接失败: " + (e != null ? e : "unknown"));
            }
        });
    }

    private void failAndRetry(String msg) {
        mainHandler.post(() -> {
            toast(msg);
            playPauseBtn.setText("▶");
            retryBtn.setVisibility(View.VISIBLE);
        });
    }

    private void playUrl(String url) {
        if (!requestAudioFocus()) {
            toast("无法获取音频焦点");
        }
        try {
            releaseMediaPlayer();
            mediaPlayer = new MediaPlayer();
            mediaPlayer.setAudioStreamType(android.media.AudioManager.STREAM_MUSIC);
            mediaPlayer.setDataSource(url);
            mediaPlayer.setVolume(1.0f, 1.0f);
            mediaPlayer.setOnPreparedListener(mp -> {
                mp.start();
                playPauseBtn.setText("⏸");
                toast("正在播放");
            });
            mediaPlayer.setOnCompletionListener(mp -> { playPauseBtn.setText("▶"); abandonAudioFocus(); });
            mediaPlayer.setOnErrorListener((mp, w, e) -> { toast("错误:" + w + "/" + e); abandonAudioFocus(); return true; });
            mediaPlayer.setOnInfoListener((mp, what, extra) -> {
                if (what == MediaPlayer.MEDIA_INFO_BUFFERING_START) toast("缓冲中...");
                if (what == MediaPlayer.MEDIA_INFO_BUFFERING_END) toast("缓冲完成");
                return false;
            });
            mediaPlayer.prepareAsync();
        } catch (Exception ex) {
            toast("播放异常: " + ex.getClass().getSimpleName() + " " + (ex.getMessage() != null ? ex.getMessage() : ""));
            abandonAudioFocus();
        }
    }

    private void playFile(String path) {
        if (path == null || path.isEmpty()) { toast("路径无效"); return; }
        try {
            java.io.File f = new java.io.File(path);
            if (!f.exists()) {
                mainHandler.post(() -> { toast("文件不存在"); retryBtn.setVisibility(View.VISIBLE); });
                return;
            }
            if (!requestAudioFocus()) {
                toast("无法获取音频焦点");
            }
            releaseMediaPlayer();
            mediaPlayer = new MediaPlayer();
            mediaPlayer.setAudioStreamType(android.media.AudioManager.STREAM_MUSIC);
            mediaPlayer.setDataSource(path);
            mediaPlayer.setOnPreparedListener(mp -> {
                mp.start();
                playPauseBtn.setText("⏸");
            });
            mediaPlayer.setOnCompletionListener(mp -> { playPauseBtn.setText("▶"); abandonAudioFocus(); });
            mediaPlayer.setOnErrorListener((mp, w, e) -> {
                mainHandler.post(() -> { toast("播放错误:" + w + "/" + e); retryBtn.setVisibility(View.VISIBLE); });
                abandonAudioFocus();
                return true;
            });
            mediaPlayer.prepareAsync();
        } catch (Exception e) {
            mainHandler.post(() -> { toast("播放失败: " + e.getMessage()); retryBtn.setVisibility(View.VISIBLE); });
            abandonAudioFocus();
        }
    }

    private void togglePlay() {
        if (mediaPlayer == null) return;
        try {
            if (mediaPlayer.isPlaying()) {
                mediaPlayer.pause();
                mainHandler.post(() -> playPauseBtn.setText("▶"));
            } else {
                mediaPlayer.start();
                mainHandler.post(() -> playPauseBtn.setText("⏸"));
            }
        } catch (IllegalStateException e) {
            Log.e(TAG, "togglePlay failed", e);
            mainHandler.post(() -> toast("播放状态异常，请重试"));
        }
    }

    private void stopPlay() {
        releaseMediaPlayer();
        abandonAudioFocus();
        miniPlayer.setVisibility(View.GONE);
        retryBtn.setVisibility(View.GONE);
    }

    private void showLoginDialog() {
        // Remove any existing overlay first
        View existing = findViewById(9999);
        if (existing != null) ((ViewGroup) existing.getParent()).removeView(existing);

        // Dark overlay that dismisses on tap
        FrameLayout overlay = new FrameLayout(this);
        loginOverlay = overlay;
        overlay.setId(9999);
        overlay.setBackgroundColor(0x99000000);
        overlay.setOnClickListener(v -> {
            ((ViewGroup) overlay.getParent()).removeView(overlay);
            loginOverlay = null;
        });
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
            LinearLayout.LayoutParams tabLP = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
            tabLP.setMargins(0, 0, 4, 0);
            tab.setLayoutParams(tabLP);
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
        loginWebContainer = webContainer;
        webContainer.setOrientation(LinearLayout.VERTICAL);
        webContainer.setBackgroundColor(0xFF0a0a0f);
        FrameLayout.LayoutParams wp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        wp.setMargins(16, 60, 16, 60);
        webContainer.setLayoutParams(wp);

        WebView wv = new WebView(this);
        loginWebView = wv;
        wv.getSettings().setJavaScriptEnabled(true);
        wv.getSettings().setDomStorageEnabled(true);
        wv.getSettings().setAllowFileAccess(false);
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
        backBtn.setOnClickListener(v -> {
            overlay.removeView(webContainer);
            if (loginWebView != null) { try { loginWebView.destroy(); } catch (Exception ignored) {} }
            loginWebView = null;
            loginWebContainer = null;
            toast("登录后点提取Cookie");
        });
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
        JSONObject loginBody = new JSONObject();
        try { loginBody.put("cookie", cookie); loginBody.put("platform", currentPlatform); } catch (Exception e) {}
        apiPost("/api/login/cookie?platform=" + currentPlatform,
            loginBody.toString(), new Callback() {
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

    // ── Cache progress timer ──

    private final Runnable cacheProgressRunnable = new Runnable() {
        @Override
        public void run() {
            long elapsed = System.currentTimeMillis() - cacheStartMs;
            if (elapsed > 30000) {
                toast("缓存时间较长，请稍候...");
            }
            mainHandler.postDelayed(this, 15000);
        }
    };

    // ── System back button handling ──

    @Override
    public void onBackPressed() {
        // WebView showing and can go back in history
        if (loginWebView != null && loginWebView.canGoBack()) {
            loginWebView.goBack();
            return;
        }
        // WebView showing but at root -> return to login sheet
        if (loginWebContainer != null && loginWebContainer.getParent() != null) {
            ((ViewGroup) loginWebContainer.getParent()).removeView(loginWebContainer);
            if (loginWebView != null) { try { loginWebView.destroy(); } catch (Exception ignored) {} }
            loginWebView = null;
            loginWebContainer = null;
            toast("登录后点提取Cookie");
            return;
        }
        // Login overlay showing -> dismiss it
        if (loginOverlay != null && loginOverlay.getParent() != null) {
            ((ViewGroup) loginOverlay.getParent()).removeView(loginOverlay);
            loginOverlay = null;
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        releaseMediaPlayer();
        if (noisyReceiver != null) {
            try { unregisterReceiver(noisyReceiver); } catch (Exception ignored) {}
            noisyReceiver = null;
        }
        abandonAudioFocus();
        // Destroy WebView if still alive (login flow may retain it)
        if (loginWebView != null) {
            try { loginWebView.destroy(); } catch (Exception ignored) {}
            loginWebView = null;
        }
        super.onDestroy();
    }

    // ── Audio Focus ──

    private boolean requestAudioFocus() {
        if (audioFocused) return true;
        if (audioManager == null) return false;
        if (Build.VERSION.SDK_INT >= 26) {
            AudioAttributes attrs = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build();
            focusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(attrs)
                .setOnAudioFocusChangeListener(this::onAudioFocusChange)
                .build();
            int res = audioManager.requestAudioFocus(focusRequest);
            audioFocused = (res == AudioManager.AUDIOFOCUS_REQUEST_GRANTED);
        } else {
            int res = audioManager.requestAudioFocus(
                this::onAudioFocusChangeLegacy,
                AudioManager.STREAM_MUSIC,
                AudioManager.AUDIOFOCUS_GAIN);
            audioFocused = (res == AudioManager.AUDIOFOCUS_REQUEST_GRANTED);
        }
        if (audioFocused) registerNoisyReceiver();
        return audioFocused;
    }

    private void abandonAudioFocus() {
        if (!audioFocused) return;
        audioFocused = false;
        if (audioManager == null) return;
        if (Build.VERSION.SDK_INT >= 26 && focusRequest != null) {
            audioManager.abandonAudioFocusRequest(focusRequest);
        } else {
            audioManager.abandonAudioFocus(this::onAudioFocusChangeLegacy);
        }
        unregisterNoisyReceiver();
    }

    private void onAudioFocusChange(int focusChange) {
        if (focusChange == AudioManager.AUDIOFOCUS_LOSS) {
            stopPlay();
        } else if (focusChange == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) {
            if (mediaPlayer != null && mediaPlayer.isPlaying()) {
                mediaPlayer.pause();
                mainHandler.post(() -> playPauseBtn.setText("▶"));
            }
        } else if (focusChange == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK) {
            if (mediaPlayer != null) {
                mediaPlayer.setVolume(0.3f, 0.3f);
            }
        } else if (focusChange == AudioManager.AUDIOFOCUS_GAIN) {
            if (mediaPlayer != null) {
                mediaPlayer.setVolume(1.0f, 1.0f);
                if (!mediaPlayer.isPlaying()) {
                    try { mediaPlayer.start(); } catch (IllegalStateException ignored) {}
                    mainHandler.post(() -> playPauseBtn.setText("⏸"));
                }
            }
        }
    }

    // Legacy callback for pre-API-26
    @SuppressWarnings("deprecation")
    private void onAudioFocusChangeLegacy(int focusChange) {
        onAudioFocusChange(focusChange);
    }

    private void registerNoisyReceiver() {
        if (noisyReceiver != null) return;
        noisyReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (AudioManager.ACTION_AUDIO_BECOMING_NOISY.equals(intent.getAction())) {
                    if (mediaPlayer != null && mediaPlayer.isPlaying()) {
                        mediaPlayer.pause();
                        mainHandler.post(() -> { playPauseBtn.setText("▶"); toast("耳机已断开"); });
                    }
                }
            }
        };
        IntentFilter filter = new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(noisyReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(noisyReceiver, filter);
        }
    }

    private void unregisterNoisyReceiver() {
        if (noisyReceiver != null) {
            try { unregisterReceiver(noisyReceiver); } catch (Exception ignored) {}
            noisyReceiver = null;
        }
    }

    private void releaseMediaPlayer() {
        if (mediaPlayer != null) {
            try {
                if (mediaPlayer.isPlaying()) mediaPlayer.stop();
                mediaPlayer.release();
            } catch (Exception ignored) {}
            mediaPlayer = null;
        }
    }

    private void apiGet(String path, Callback cb) {
        apiExecutor.execute(() -> {
            HttpURLConnection c = null;
            try {
                URL u = new URL(API + path);
                c = (HttpURLConnection) u.openConnection();
                c.setRequestMethod("GET");
                c.setConnectTimeout(5000);
                c.setReadTimeout(15000);
                String resp = readStream(c.getInputStream());
                cb.onResult(new JSONObject(resp));
            } catch (Exception e) { cb.onError(e.getMessage()); }
            finally { if (c != null) c.disconnect(); }
        });
    }

    private void apiPost(String path, String body, Callback cb) {
        apiExecutor.execute(() -> {
            HttpURLConnection c = null;
            try {
                URL u = new URL(API + path);
                c = (HttpURLConnection) u.openConnection();
                c.setRequestMethod("POST");
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setConnectTimeout(5000);
                c.setReadTimeout(15000);
                c.getOutputStream().write(body.getBytes("UTF-8"));
                String resp = readStream(c.getInputStream());
                cb.onResult(new JSONObject(resp));
            } catch (Exception e) { cb.onError(e.getMessage()); }
            finally { if (c != null) c.disconnect(); }
        });
    }

    private String readStream(InputStream is) throws IOException {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(is, "UTF-8"))) {
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
        }
        return sb.toString();
    }

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
