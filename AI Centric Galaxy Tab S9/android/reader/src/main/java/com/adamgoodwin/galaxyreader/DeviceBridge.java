package com.adamgoodwin.galaxyreader;

import android.accessibilityservice.AccessibilityService;
import android.app.ActivityManager;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ApplicationInfo;
import android.graphics.Rect;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.util.Xml;
import org.json.JSONObject;
import org.xmlpull.v1.XmlSerializer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;

/** Authenticated, loopback-only device tools. No remote listener or shell. */
public final class DeviceBridge extends AccessibilityService {
    private static final String OUTLOOK="com.microsoft.office.outlook", GALAXY="com.adamgoodwin.galaxyworkspace";
    private final Handler main=new Handler(Looper.getMainLooper());
    private volatile ServerSocket server;
    private volatile boolean closing;
    private byte[] key;
    private int nodes;
    private int checkedNodes;
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override protected void onServiceConnected() {
        if(server!=null && !server.isClosed())return;
        closing=false;
        new Thread(this::serve,"Galaxy-device-tools").start();
    }
    @Override public void onDestroy() {
        closing=true;
        try { if(server!=null)server.close(); } catch(IOException ignored) { }
        server=null; super.onDestroy();
    }
    private void serve() {
        try {
            key=java.nio.file.Files.readAllBytes(new File(getFilesDir(),"bridge.key").toPath());
            if(key.length!=64)return;
            ServerSocket listener=new ServerSocket();
            listener.setReuseAddress(true);
            listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),48442),4);
            server=listener;android.util.Log.i("GalaxyDeviceTools","Loopback service started");
            while(!closing && !listener.isClosed() && server==listener) {
                try(Socket client=listener.accept()) { client.setSoTimeout(4000);android.util.Log.i("GalaxyDeviceTools","Accepted local connection"); handle(client);android.util.Log.i("GalaxyDeviceTools","Local request finished"); }
                catch(Exception e) { android.util.Log.i("GalaxyDeviceTools","Local connection ended: "+e.getClass().getSimpleName()); }
            }
        } catch(Exception ignored) { /* Setup is checked by Galaxy's connection status. */ }
    }
    private String line(InputStream in) throws IOException {
        ByteArrayOutputStream b=new ByteArrayOutputStream(); int c;
        while((c=in.read())!=-1 && c!='\n') { if(b.size()>2048)throw new IOException(); if(c!='\r')b.write(c); }
        return b.toString(StandardCharsets.US_ASCII);
    }
    private void handle(Socket client) throws Exception {
        InputStream in=client.getInputStream();
        if(!"POST /device HTTP/1.1".equals(line(in)))return;
        int length=-1; String auth=""; boolean host=false;
        for(int i=0;i<20;i++) {
            String s=line(in); if(s.isEmpty())break;
            int colon=s.indexOf(':'); if(colon<1)return;
            String name=s.substring(0,colon).toLowerCase(Locale.ROOT), value=s.substring(colon+1).trim();
            if(name.equals("content-length"))length=Integer.parseInt(value);
            if(name.equals("authorization"))auth=value;
            if(name.equals("host"))host=value.equals("127.0.0.1:48442");
            if(name.equals("origin") || name.equals("transfer-encoding"))return;
        }
        if(!host || length<2 || length>12000 || !MessageDigest.isEqual(("Bearer "+new String(key,StandardCharsets.US_ASCII)).getBytes(StandardCharsets.US_ASCII),auth.getBytes(StandardCharsets.US_ASCII)))return;
        byte[] body=in.readNBytes(length); if(body.length!=length)return;
        JSONObject response=new JSONObject();
        try {
            JSONObject request=new JSONObject(new String(body,StandardCharsets.UTF_8));
            FutureTask<JSONObject> task=new FutureTask<>(()->dispatch(request));
            main.post(task);
            try { response.put("result",task.get(5,TimeUnit.SECONDS)); }
            finally { if(!task.isDone())task.cancel(false); }
        } catch(Exception e) {
            Throwable cause=e instanceof ExecutionException?e.getCause():e;
            response.put("error",cause instanceof IllegalStateException?cause.getMessage():"Device tool could not complete. Keep the tablet unlocked and try again.");
        }
        byte[] bytes=response.toString().getBytes(StandardCharsets.UTF_8);
        OutputStream out=client.getOutputStream();
        out.write(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: "+bytes.length+"\r\n\r\n").getBytes(StandardCharsets.US_ASCII));out.write(bytes);out.flush();
    }
    private AccessibilityNodeInfo focusedOutlook() {
        AccessibilityNodeInfo active=getRootInActiveWindow();
        if(active==null || !OUTLOOK.contentEquals(active.getPackageName()==null?"":active.getPackageName()))
            throw new IllegalStateException("Outlook lost focus. Return to Galaxy and try the request again.");
        return active;
    }
    private AccessibilityNodeInfo outlook() {
        AccessibilityNodeInfo active=focusedOutlook();checkedNodes=0;check(active,0);return active;
    }
    private void check(AccessibilityNodeInfo n,int depth) {
        if(depth>70 || ++checkedNodes>1800)throw new IllegalStateException("Outlook screen exceeded the reader limit.");
        if(n.isPassword())throw new IllegalStateException("Complete sign-in yourself in Outlook.");
        String id=String.valueOf(n.getViewIdResourceName());
        if(id.contains("compose_subject") || id.contains("compose_body") || id.contains("recipient_edit") || id.contains("compose_to"))
            throw new IllegalStateException("Close the Outlook message editor before reading.");
        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null)check(c,depth+1);}
    }
    private JSONObject dispatch(JSONObject data) throws Exception {
        String op=data.optString("operation"); JSONObject r=new JSONObject();
        if(op.equals("identity"))return r.put("model",Build.MODEL).put("bridgeId",hex(MessageDigest.getInstance("SHA-256").digest(key)));
        if(op.equals("foreground")) { focusedOutlook();return r.put("outlook",true); }
        if(op.equals("open")) {
            try { focusedOutlook(); } catch(IllegalStateException e) {
                Intent i=getPackageManager().getLaunchIntentForPackage(OUTLOOK);
                if(i==null)throw new IllegalStateException("Install Outlook first.");
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_REORDER_TO_FRONT|Intent.FLAG_ACTIVITY_SINGLE_TOP);startActivity(i);
            }
            return r;
        }
        if(op.equals("return")) {
            try { outlook(); }catch(IllegalStateException e){return r.put("returned",false);}
            Intent i=getPackageManager().getLaunchIntentForPackage(GALAXY);
            if(i!=null){i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_REORDER_TO_FRONT|Intent.FLAG_ACTIVITY_SINGLE_TOP);startActivity(i);}
            return r.put("returned",true);
        }
        if(op.equals("snapshot")) {
            nodes=0;StringWriter writer=new StringWriter();XmlSerializer xml=Xml.newSerializer();xml.setOutput(writer);
            xml.startTag("","hierarchy");writeNode(xml,outlook(),0);xml.endTag("","hierarchy");xml.flush();
            if(writer.toString().length()>500000)throw new IllegalStateException("Outlook screen is too large.");
            return r.put("xml",writer.toString());
        }
        if(op.equals("back")) { outlook();if(!performGlobalAction(GLOBAL_ACTION_BACK))throw new IllegalStateException("Outlook could not go back.");return r; }
        if(op.equals("search_text")) {
            String query=data.getString("query");if(!query.matches("[A-Za-z0-9 @._:+\\-]{1,120}"))throw new IllegalStateException("Use a short text search.");
            List<AccessibilityNodeInfo> found=outlook().findAccessibilityNodeInfosByViewId(OUTLOOK+":id/search_edit_text");
            if(found.size()!=1)throw new IllegalStateException("Open Outlook search first.");
            Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,query);
            if(!found.get(0).performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args))throw new IllegalStateException("Outlook did not accept the search.");return r;
        }
        if(op.equals("enter")) {
            List<AccessibilityNodeInfo> found=outlook().findAccessibilityNodeInfosByViewId(OUTLOOK+":id/search_edit_text");
            if(found.size()==1)found.get(0).performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.getId());return r;
        }
        if(op.equals("tap")) {
            JSONObject target=data.getJSONObject("node");AccessibilityNodeInfo n=find(outlook(),target,0);
            if(n==null || !allowed(n))throw new IllegalStateException("That Outlook control moved or is not a reading control. Read the screen again.");
            if(!n.performAction(AccessibilityNodeInfo.ACTION_CLICK))throw new IllegalStateException("Outlook did not open that control.");return r;
        }
        if(op.equals("scroll")) {
            boolean down="down".equals(data.optString("direction"));
            if(!down && !"up".equals(data.optString("direction")))throw new IllegalStateException("Choose up or down.");
            AccessibilityNodeInfo root=outlook();
            for(String id:new String[]{"message_details_nested_scrolling_recycler_view","conversations_recycler_view","agenda_view","recycler_view","conversation_list"})
                for(AccessibilityNodeInfo n:root.findAccessibilityNodeInfosByViewId(OUTLOOK+":id/"+id))
                    if(n.isVisibleToUser() && n.isScrollable() && n.performAction(down?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD))return r;
            throw new IllegalStateException("No readable Outlook content could be scrolled.");
        }
        if(op.equals("property")) {
            String name=data.optString("name");
            if(name.equals("ro.product.model"))return r.put("value",Build.MODEL);
            if(name.equals("ro.build.version.release"))return r.put("value",Build.VERSION.RELEASE);
            if(name.equals("ro.build.version.security_patch"))return r.put("value",Build.VERSION.SECURITY_PATCH);
        }
        if(op.equals("battery")) {
            Intent b=registerReceiver(null,new IntentFilter(Intent.ACTION_BATTERY_CHANGED));if(b==null)throw new IllegalStateException("Battery data unavailable.");
            return r.put("value","level: "+b.getIntExtra(BatteryManager.EXTRA_LEVEL,-1)+"\ntemperature: "+b.getIntExtra(BatteryManager.EXTRA_TEMPERATURE,-1)+"\nstatus: "+b.getIntExtra(BatteryManager.EXTRA_STATUS,-1)+"\nUSB powered: "+(b.getIntExtra(BatteryManager.EXTRA_PLUGGED,0)==BatteryManager.BATTERY_PLUGGED_USB));
        }
        if(op.equals("memory")) { ActivityManager.MemoryInfo m=new ActivityManager.MemoryInfo();getSystemService(ActivityManager.class).getMemoryInfo(m);return r.put("value","MemTotal: "+m.totalMem/1024+" kB\nMemAvailable: "+m.availMem/1024+" kB"); }
        if(op.equals("apps")) {
            StringBuilder list=new StringBuilder();for(ApplicationInfo a:getPackageManager().getInstalledApplications(0))if((a.flags&ApplicationInfo.FLAG_SYSTEM)==0)list.append("package:").append(a.packageName).append('\n');return r.put("value",list.toString());
        }
        if(op.equals("setting"))return setting(data);
        throw new IllegalStateException("Unsupported device tool.");
    }
    private JSONObject setting(JSONObject data) throws Exception {
        String name=data.getString("name"), action=data.getString("action"),value=data.optString("value");
        boolean secure=name.equals("show_ime_with_hard_keyboard");
        if(!secure && !Arrays.asList("screen_off_timeout","screen_brightness_mode","accelerometer_rotation").contains(name))throw new IllegalStateException("Unsupported setting.");
        if(!Arrays.asList("get","put","delete").contains(action))throw new IllegalStateException("Unsupported setting action.");
        if(action.equals("put") && !(name.equals("screen_off_timeout")?Arrays.asList("30000","60000","120000","300000","600000","1800000").contains(value):Arrays.asList("0","1").contains(value)))throw new IllegalStateException("Unsupported setting value.");
        if(!action.equals("get")) {
            String next=action.equals("delete")?null:value;
            boolean ok=secure?Settings.Secure.putString(getContentResolver(),name,next):Settings.System.putString(getContentResolver(),name,next);
            if(!ok)throw new IllegalStateException("Android did not accept the setting.");
        }
        String result=secure?Settings.Secure.getString(getContentResolver(),name):Settings.System.getString(getContentResolver(),name);
        return new JSONObject().put("value",result==null?"null":result);
    }
    private String text(CharSequence value){return value==null?"":value.toString();}
    private String bounds(AccessibilityNodeInfo n){Rect r=new Rect();n.getBoundsInScreen(r);return "["+r.left+","+r.top+"]["+r.right+","+r.bottom+"]";}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo n,JSONObject target,int depth) throws Exception {
        if(depth>70)return null;
        if(n.isVisibleToUser() && n.isEnabled() && n.isClickable() && OUTLOOK.contentEquals(n.getPackageName()==null?"":n.getPackageName()) &&
           text(n.getViewIdResourceName()).equals(target.optString("resource-id")) && text(n.getText()).equals(target.optString("text")) &&
           text(n.getContentDescription()).equals(target.optString("content-desc")) && bounds(n).equals(target.optString("bounds")))return n;
        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null){AccessibilityNodeInfo match=find(c,target,depth+1);if(match!=null)return match;}}return null;
    }
    private boolean allowed(AccessibilityNodeInfo n) {
        String id=text(n.getViewIdResourceName()).replace(OUTLOOK+":id/",""),desc=text(n.getContentDescription()),label=text(n.getText());
        if(Arrays.asList("message_snippet_frontview","menu_calendar_views","calendar_month_title_button","search_cancel_btn","search_edit_text").contains(id))return true;
        if(id.equals("message_open_details") && desc.equals("Open full message"))return true;
        if(id.equals("message_header") && desc.startsWith("Message "))return true;
        if(Arrays.asList("Mail","Calendar","All Accounts","Open Navigation Drawer","Search","All").contains(desc) || label.equals("Agenda"))return true;
        if(desc.matches("Suggested search , Text, Search for \"[A-Za-z0-9 @._:+\\-]{1,120}\""))return true;
        return desc.matches("(?:Events on )?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), .*") && !desc.contains("Work location:");
    }
    private void writeNode(XmlSerializer xml,AccessibilityNodeInfo n,int depth) throws Exception {
        if(++nodes>1800 || depth>70)throw new IllegalStateException("Outlook screen exceeded the reader limit.");
        if(!n.isVisibleToUser()){for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null)writeNode(xml,c,depth+1);}return;}
        xml.startTag("","node");
        attr(xml,"package",n.getPackageName());attr(xml,"resource-id",n.getViewIdResourceName());attr(xml,"class",n.getClassName());attr(xml,"text",n.getText());attr(xml,"content-desc",n.getContentDescription());
        attr(xml,"clickable",String.valueOf(n.isClickable()));attr(xml,"enabled",String.valueOf(n.isEnabled()));attr(xml,"scrollable",String.valueOf(n.isScrollable()));attr(xml,"password","false");attr(xml,"bounds",bounds(n));
        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null)writeNode(xml,c,depth+1);}xml.endTag("","node");
    }
    private void attr(XmlSerializer xml,String key,CharSequence value)throws Exception{xml.attribute("",key,text(value).replaceAll("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]",""));}
    private String hex(byte[] bytes){StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format(Locale.ROOT,"%02x",b&255));return s.toString();}
}
