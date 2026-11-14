package au.zac.acreagefinder;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** Acreage Finder: the land finder page in a WebView. Shows the newest listings it has, and fetches
 *  fresh ones (refreshed hourly by the scanner) in the background each time it is opened. */
public class MainActivity extends Activity {
    static final String BASE =
        "https://raw.githubusercontent.com/Zeus4127/bargain-finder/ccr-37547555-829az5/acreage/";
    static final String DATA_URL = BASE + "acreage-data.js";
    static final long CHECK_EVERY_MS = 15 * 60 * 1000L;
    WebView web;
    long lastCheck = 0;
    final Handler ui = new Handler(Looper.getMainLooper());

    File dataFile() { return new File(getFilesDir(), "acreage-data.js"); }

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setTextZoom(100);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if ("file".equals(u.getScheme())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { }
                return true;   // listings open in the phone's browser
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                String p = r.getUrl().toString();
                File f = dataFile();
                if (p.endsWith("/acreage-data.js") && f.length() > 100000) {
                    try { return new WebResourceResponse("application/javascript", "utf-8", new FileInputStream(f)); }
                    catch (Exception e) { }
                }
                File pg = new File(getFilesDir(), "acreage.html"), hd = new File(getFilesDir(), "history-data.js");
                if (p.endsWith("/index.html") && pg.length() > 20000) {
                    try { return new WebResourceResponse("text/html", "utf-8", new FileInputStream(pg)); } catch (Exception e) { }
                }
                if (p.endsWith("/history-data.js") && hd.length() > 10000) {
                    try { return new WebResourceResponse("application/javascript", "utf-8", new FileInputStream(hd)); } catch (Exception e) { }
                }
                return null;
            }
        });
        web.setWebChromeClient(new android.webkit.WebChromeClient());
        setContentView(web);
        if (b != null) web.restoreState(b); else web.loadUrl("file:///android_asset/index.html");
        // background check for new Standouts and rule matches, shown as phone notifications
        AlertJob.schedule(this);
        if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 7);
        new Thread(new Runnable() { public void run() { try { AlertJob.check(getApplicationContext()); } catch (Exception e) { } } }).start();
    }

    @Override protected void onSaveInstanceState(Bundle b) { super.onSaveInstanceState(b); web.saveState(b); }

    @Override protected void onResume() {
        super.onResume();
        long now = System.currentTimeMillis();
        if (now - lastCheck > CHECK_EVERY_MS) { lastCheck = now; fetchNewData(); }
    }

    @Override public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }

    /** Download the newest listings; if they are newer than what is showing, offer a one-tap refresh. */
    void fetchNewData() {
        new Thread(new Runnable() { public void run() {
            fetchFile("acreage.html", "<title>Acreage Finder", 20000);
            fetchFile("history-data.js", "window.HISTORY_DATA", 10000);
            File tmp = new File(getFilesDir(), "acreage-data.tmp");
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(DATA_URL + "?t=" + System.currentTimeMillis() / 60000).openConnection();
                c.setConnectTimeout(15000); c.setReadTimeout(60000);
                if (c.getResponseCode() != 200) return;
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(tmp)) {
                    byte[] buf = new byte[65536]; int n;
                    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                }
                String head = readHead(tmp, 200);
                if (!head.startsWith("window.ACREAGE_DATA=") || tmp.length() < 100000) { tmp.delete(); return; }
                String newScan = scannedOf(head), oldScan = dataFile().exists() ? scannedOf(readHead(dataFile(), 200)) : "";
                if (newScan.equals(oldScan)) { tmp.delete(); return; }
                if (!tmp.renameTo(dataFile())) return;
                final String when = newScan;
                ui.post(new Runnable() { public void run() { web.evaluateJavascript(
                    "(function(){var sc=(window.ACREAGE_DATA||{}).scanned||'';if(sc>='" + when + "')return;" +
                    "var d=document.createElement('div');d.textContent='New listings are ready. Tap to refresh.';" +
                    "d.style.cssText='position:fixed;left:12px;right:12px;bottom:16px;z-index:9999;background:#2F7D4F;color:#fff;" +
                    "padding:14px 16px;border-radius:14px;font:600 16px system-ui;text-align:center;box-shadow:0 4px 14px rgba(0,0,0,.25)';" +
                    "d.onclick=function(){location.reload()};document.body.appendChild(d)})()", null); }});
            } catch (Exception e) {
                tmp.delete();   // no internet: keep showing what we have
            }
        }}).start();
    }

    /** Download one small file of the app (page or growth data) if it looks right; used next time the page loads. */
    void fetchFile(String name, String mustStart, long minSize) {
        File tmp = new File(getFilesDir(), name + ".tmp");
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(BASE + name + "?t=" + System.currentTimeMillis() / 60000).openConnection();
            c.setConnectTimeout(15000); c.setReadTimeout(60000);
            if (c.getResponseCode() != 200) return;
            try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(tmp)) {
                byte[] buf = new byte[65536]; int n;
                while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            }
            if (tmp.length() >= minSize && readHead(tmp, 60).toLowerCase().startsWith(mustStart.toLowerCase())) tmp.renameTo(new File(getFilesDir(), name));
            else tmp.delete();
        } catch (Exception e) { tmp.delete(); }
    }

    static String readHead(File f, int n) {
        try (FileInputStream in = new FileInputStream(f)) { byte[] b = new byte[n]; int k = in.read(b); return k > 0 ? new String(b, 0, k, "UTF-8") : ""; }
        catch (Exception e) { return ""; }
    }
    static String scannedOf(String head) {
        int i = head.indexOf("\"scanned\":\""); if (i < 0) return "";
        int j = head.indexOf('"', i + 11); return j > i ? head.substring(i + 11, j) : "";
    }
}
