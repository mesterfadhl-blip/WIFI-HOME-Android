package com.wifihome.app;

import android.app.*;
import android.os.*;
import android.content.*;
import android.net.Uri;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.webkit.*;
import android.widget.Toast;

public class MainActivity extends Activity {
    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private static final int FILE_CHOOSER = 501;

    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        web = new WebView(this);
        setContentView(web);
        WebSettings s=web.getSettings();
        s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true); s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true); s.setAllowContentAccess(true); s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false); s.setLoadWithOverviewMode(true); s.setUseWideViewPort(true);
        if(Build.VERSION.SDK_INT>=21) s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        web.addJavascriptInterface(new Bridge(),"WifiHomeAndroid");
        web.setWebViewClient(new WebViewClient(){
            @Override public void onPageFinished(WebView v,String url){
                v.evaluateJavascript("(function(){window.print=function(){WifiHomeAndroid.printPage();};document.documentElement.setAttribute('data-app','android');})();",null);
            }
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView w,ValueCallback<Uri[]> cb,FileChooserParams p){
                if(fileCallback!=null) fileCallback.onReceiveValue(null); fileCallback=cb;
                try{startActivityForResult(p.createIntent(),FILE_CHOOSER);}catch(Exception e){fileCallback=null;Toast.makeText(MainActivity.this,"تعذر فتح الملفات",Toast.LENGTH_SHORT).show();}
                return true;
            }
        });
        web.loadUrl("file:///android_asset/index.html");
    }
    public class Bridge {
        @JavascriptInterface public void printPage(){ runOnUiThread(()->{
            PrintManager pm=(PrintManager)getSystemService(PRINT_SERVICE);
            pm.print("WIFI-HOME",web.createPrintDocumentAdapter("WIFI-HOME"),new PrintAttributes.Builder().build());
        }); }
        @JavascriptInterface public void toast(String m){runOnUiThread(()->Toast.makeText(MainActivity.this,m,Toast.LENGTH_SHORT).show());}
    }
    @Override protected void onActivityResult(int r,int c,Intent d){super.onActivityResult(r,c,d);if(r==FILE_CHOOSER&&fileCallback!=null){fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(c,d));fileCallback=null;}}
    @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
}
