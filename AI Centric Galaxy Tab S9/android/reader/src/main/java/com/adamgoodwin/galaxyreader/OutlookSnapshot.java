package com.adamgoodwin.galaxyreader;

import android.app.Instrumentation;
import android.app.UiAutomation;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.util.Base64;
import android.util.Xml;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import org.xmlpull.v1.XmlSerializer;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;

/** One-shot visible Outlook reader, invoked through authorized ADB instrumentation.
 * No activity, background service, network, account access, input or file access.
 */
public final class OutlookSnapshot extends Instrumentation {
    private static final String OUTLOOK = "com.microsoft.office.outlook";
    private int count;
    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); start(); }
    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            UiAutomation automation = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
            AccessibilityServiceInfo info = automation.getServiceInfo();
            info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS | AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
            automation.setServiceInfo(info);
            // Outlook rebuilds Compose semantics when an automation reader
            // attaches. Allow that bounded update before requesting the tree.
            SystemClock.sleep(1000);
            if (android.os.Build.VERSION.SDK_INT >= 34) automation.clearCache();
            AccessibilityNodeInfo root = null;
            for (int attempt = 0; attempt < 10 && root == null; attempt++) {
                for (AccessibilityWindowInfo window : automation.getWindows()) {
                    AccessibilityNodeInfo candidate = window.getRoot();
                    if (candidate != null && OUTLOOK.contentEquals(candidate.getPackageName() == null ? "" : candidate.getPackageName())) {
                        root = candidate; break;
                    }
                }
                if (root == null) SystemClock.sleep(150);
            }
            if (root == null) throw new IllegalStateException("Outlook has no readable visible window. Unlock the tablet and open Outlook.");
            StringWriter writer = new StringWriter();
            XmlSerializer xml = Xml.newSerializer(); xml.setOutput(writer);
            xml.startDocument("UTF-8", true); xml.startTag("", "hierarchy");
            writeNode(xml, root, 0); xml.endTag("", "hierarchy"); xml.endDocument();
            byte[] bytes = writer.toString().getBytes(StandardCharsets.UTF_8);
            if (bytes.length > 500000) throw new IllegalStateException("Outlook screen is too large. Narrow the view.");
            result.putString("galaxy", Base64.encodeToString(bytes, Base64.NO_WRAP));
            finish(-1, result);
        } catch (Exception error) {
            result.putString("galaxy_error", error instanceof IllegalStateException ? error.getMessage() : "Could not read the visible Outlook window.");
            finish(0, result);
        }
    }
    private void writeNode(XmlSerializer xml, AccessibilityNodeInfo n, int depth) throws Exception {
        if (++count > 1800 || depth > 70) throw new IllegalStateException("Outlook screen exceeded the reader limit.");
        // Layout-only ancestors can be hidden from accessibility while their
        // message rows are visible. Traverse them without recording their data.
        if (!n.isVisibleToUser()) {
            for (int i=0; i<n.getChildCount(); i++) { AccessibilityNodeInfo child=n.getChild(i); if(child!=null) writeNode(xml,child,depth+1); }
            return;
        }
        if (n.isPassword()) throw new IllegalStateException("A sign-in field is visible. Complete sign-in yourself in Outlook.");
        Rect r = new Rect(); n.getBoundsInScreen(r);
        xml.startTag("", "node");
        attr(xml, "package", n.getPackageName()); attr(xml, "resource-id", n.getViewIdResourceName());
        attr(xml, "class", n.getClassName()); attr(xml, "text", n.getText()); attr(xml, "content-desc", n.getContentDescription());
        attr(xml, "clickable", String.valueOf(n.isClickable())); attr(xml, "enabled", String.valueOf(n.isEnabled()));
        attr(xml, "scrollable", String.valueOf(n.isScrollable())); attr(xml, "password", "false");
        attr(xml, "bounds", "["+r.left+","+r.top+"]["+r.right+","+r.bottom+"]");
        for (int i=0; i<n.getChildCount(); i++) { AccessibilityNodeInfo child=n.getChild(i); if(child!=null) writeNode(xml,child,depth+1); }
        xml.endTag("", "node");
    }
    private void attr(XmlSerializer xml, String name, CharSequence value) throws Exception {
        String s = value == null ? "" : value.toString();
        xml.attribute("", name, s.replaceAll("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]", ""));
    }
}
