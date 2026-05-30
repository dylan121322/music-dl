package com.musicdl;

import android.os.Bundle;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
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

    /** JavaScript bridge: called from web frontend to interact with Android */
    public class AppBridge {
        @JavascriptInterface
        public void toast(String msg) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show());
        }

        @JavascriptInterface
        public String getCookies(String domain) {
            String cookies = CookieManager.getInstance().getCookie(domain);
            Log.i(TAG, "Cookies for " + domain + ": " + (cookies != null ? cookies.substring(0, Math.min(50, cookies.length())) + "..." : "null"));
            return cookies != null ? cookies : "";
        }

        @JavascriptInterface
        public void loginPlatform(String platform, String url) {
            // Navigate WebView to platform login page
            runOnUiThread(() -> {
                Toast.makeText(MainActivity.this, "请在页面中登录，完成后按返回键", Toast.LENGTH_LONG).show();
                webView.loadUrl(url);
            });
        }

        @JavascriptInterface
        public void goHome() {
            runOnUiThread(() -> webView.loadUrl(URL));
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Log.i(TAG, "Starting Music DL...");

        webView = new WebView(this);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.KITKAT) {
            WebView.setWebContentsDebuggingEnabled(true);
        }
        setContentView(webView);

        // Enable cookies for login
        CookieManager.getInstance().setAcceptCookie(true);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        // Desktop UA: avoids mobile redirect to app download pages on music platforms
        settings.setUserAgentString("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36");

        // Register JS bridge
        webView.addJavascriptInterface(new AppBridge(), "Android");

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
                // If we navigated away for login and now came back to Music DL, inject cookie helper
                if (url != null && url.startsWith(URL)) {
                    view.loadUrl("javascript:if(window.onAndroidCookiesReady){window.onAndroidCookiesReady()}");
                }
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
