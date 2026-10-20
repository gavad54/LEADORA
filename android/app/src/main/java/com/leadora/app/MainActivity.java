package com.leadora.app;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceError;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.content.Intent;
import android.net.Uri;

public class MainActivity extends Activity {
    private static final String HOME = "https://leadora-web-production.up.railway.app/";
    private WebView web;
    private LinearLayout offline;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.rgb(16, 27, 53));
        getWindow().setNavigationBarColor(Color.rgb(16, 27, 53));
        buildLayout();
        configureWebView();
        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else web.loadUrl(HOME);
    }

    private void buildLayout() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(16,27,53));
        web = new WebView(this);
        root.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
        offline = new LinearLayout(this);
        offline.setOrientation(LinearLayout.VERTICAL);
        offline.setGravity(android.view.Gravity.CENTER);
        offline.setPadding(28,28,28,28);
        offline.setBackgroundColor(Color.rgb(16,27,53));
        TextView title = new TextView(this);
        title.setText("LEADORA");
        title.setTextColor(Color.rgb(95,224,255));
        title.setTextSize(28);
        title.setGravity(android.view.Gravity.CENTER);
        TextView message = new TextView(this);
        message.setText("اتصال به سامانه برقرار نشد. اینترنت را بررسی کنید و دوباره تلاش کنید.");
        message.setTextColor(Color.WHITE);
        message.setTextSize(16);
        message.setGravity(android.view.Gravity.CENTER);
        message.setPadding(0,20,0,20);
        TextView retry = new TextView(this);
        retry.setText("تلاش دوباره");
        retry.setTextColor(Color.rgb(16,27,53));
        retry.setBackgroundColor(Color.rgb(103,223,205));
        retry.setPadding(28,14,28,14);
        retry.setGravity(android.view.Gravity.CENTER);
        retry.setOnClickListener(v -> { offline.setVisibility(View.GONE); web.setVisibility(View.VISIBLE); web.loadUrl(HOME); });
        offline.addView(title);
        offline.addView(message);
        offline.addView(retry);
        offline.setVisibility(View.GONE);
        root.addView(offline, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
    }

    private void configureWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadsImagesAutomatically(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setBackgroundColor(Color.rgb(244,246,251));
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String host = uri.getHost();
                if ("leadora-web-production.up.railway.app".equalsIgnoreCase(host)) return false;
                if ("https".equalsIgnoreCase(uri.getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) { }
                    return true;
                }
                return true;
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    web.setVisibility(View.GONE);
                    offline.setVisibility(View.VISIBLE);
                }
            }
        });
    }

    @Override protected void onSaveInstanceState(Bundle outState) {
        web.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override public void onBackPressed() {
        if (web != null && web.getVisibility() == View.VISIBLE && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (web != null) { web.stopLoading(); web.destroy(); }
        super.onDestroy();
    }
}