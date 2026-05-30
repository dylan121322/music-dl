package com.musicdl;

import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.appcompat.app.AppCompatActivity;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends AppCompatActivity {
    private WebView webView;
    private static final String URL = "http://127.0.0.1:8765";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Start Python server
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        new Thread(() -> {
            Python.getInstance().getModule("server_runner").callAttr("run_server");
        }).start();

        // Setup WebView
        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, int errorCode,
                                         String description, String failingUrl) {
                // Retry after a delay (server might still be starting)
                view.postDelayed(() -> view.loadUrl(URL), 1000);
            }
        });

        // Wait for server then load
        webView.postDelayed(() -> webView.loadUrl(URL), 2000);
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
