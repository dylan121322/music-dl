package com.musicdl;

import android.os.Bundle;
import android.util.Log;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends AppCompatActivity {
    private static final String TAG = "MusicDL";
    private static final String URL = "http://127.0.0.1:8765";
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Log.i(TAG, "Starting Music DL...");

        // Setup WebView first (will show error page if server fails)
        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, int errorCode,
                                         String description, String failingUrl) {
                Log.w(TAG, "WebView error: " + description);
                view.postDelayed(() -> view.loadUrl(URL), 1500);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                Log.i(TAG, "Page loaded: " + url);
            }
        });

        // Start Python server in background
        new Thread(() -> {
            try {
                Log.i(TAG, "Starting Python...");
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(MainActivity.this));
                }
                Log.i(TAG, "Python started, running server...");
                Python.getInstance().getModule("server_runner").callAttr("run_server");
            } catch (Exception e) {
                Log.e(TAG, "Python failed: " + e.getMessage(), e);
                runOnUiThread(() -> {
                    String html = "<html><body style='background:#0b0c10;color:#e0e0e0;padding:40px;" +
                        "font-family:sans-serif;'><h2>启动失败</h2><p>" +
                        e.getMessage().replace("<", "&lt;") +
                        "</p><p style='color:#7a7f8e;'>请检查依赖是否完整安装</p></body></html>";
                    webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
                    Toast.makeText(MainActivity.this, "启动失败: " + e.getMessage(),
                                   Toast.LENGTH_LONG).show();
                });
            }
        }).start();

        // Load after delay to let server start
        webView.postDelayed(() -> {
            Log.i(TAG, "Loading " + URL);
            webView.loadUrl(URL);
        }, 2500);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
