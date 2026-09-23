package com.adamgoodwin.galaxyworkspace;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.ClipData;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.Icon;
import android.graphics.drawable.RippleDrawable;
import android.content.res.ColorStateList;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Message;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.ValueCallback;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.io.File;
import java.io.FileOutputStream;
import androidx.core.content.FileProvider;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** Native launcher and connection UI, with the shared workspace in a restricted WebView. */
public final class MainActivity extends Activity {
    private static final int PAPER = Color.rgb(245, 244, 239);
    private static final int INK = Color.rgb(21, 29, 38);
    private static final int MUTED = Color.rgb(99, 109, 104);
    private static final int SAGE = Color.rgb(190, 209, 186);
    private static final int GREEN = Color.rgb(60, 88, 69);
    private static final int LINE = Color.rgb(220, 225, 216);
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final AtomicInteger healthGeneration = new AtomicInteger();
    private final java.util.List<WebView> popups = new java.util.ArrayList<>();
    private SharedPreferences preferences;
    private String origin;
    private LinearLayout root;
    private ScrollView home;
    private LinearLayout workspace;
    private FrameLayout webArea;
    private LinearLayout errorCard;
    private WebView browser;
    private ProgressBar progress;
    private TextView connectionState;
    private TextView connectionHint;
    private Button checkButton;
    private boolean showingWorkspace;
    private boolean loadFailed;
    private boolean firstHome = true;
    private static final int PICK_FILES = 41;
    private static final int SAVE_REPORT = 42;
    private ValueCallback<Uri[]> fileSelection;
    private String selectionOrigin;
    private byte[] reportDownload;
    private boolean downloading;
    private String downloadName, downloadType, downloadUrl;
    private AlertDialog connectionDialog;
    private PendingIntent pairingResult;
    private String pairingAction;
    private static java.lang.ref.WeakReference<MainActivity> active = new java.lang.ref.WeakReference<>(null);

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        active = new java.lang.ref.WeakReference<>(this);
        preferences = getSharedPreferences("workspace", MODE_PRIVATE);
        try { origin = WorkspaceAddress.normalize(preferences.getString("origin", WorkspaceAddress.USB)); }
        catch (IllegalArgumentException ignored) { origin = WorkspaceAddress.USB; }
        getWindow().setDecorFitsSystemWindows(false);
        root = column();
        root.setBackgroundColor(PAPER);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            android.graphics.Insets keyboard = insets.getInsets(WindowInsets.Type.ime());
            view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, keyboard.bottom));
            return insets;
        });
        setContentView(root);
        getWindow().getInsetsController().setSystemBarsAppearance(
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
        getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0, this::navigateBack);
        showHome();
        if (preferences.getBoolean("localEngine", false)) startLocalEngine();
        if (savedInstanceState != null && savedInstanceState.getBoolean("workspace")) openWorkspace();
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }
    private LinearLayout row() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        return layout;
    }
    private GradientDrawable surface(int color, int radius, boolean border) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        if (border) drawable.setStroke(dp(1), LINE);
        return drawable;
    }
    private TextView text(String value, float size, int color, String family) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setTypeface(Typeface.create(family, Typeface.NORMAL));
        view.setIncludeFontPadding(false);
        view.setLineSpacing(dp(3), 1);
        return view;
    }
    private void gap(LinearLayout parent, int height) {
        parent.addView(new View(this), new LinearLayout.LayoutParams(1, dp(height)));
    }
    private void weighted(LinearLayout parent, View child) {
        parent.addView(child, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
    }
    private Button button(String label, boolean primary, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(15);
        button.setTextColor(primary ? Color.WHITE : INK);
        button.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        button.setMinHeight(dp(52));
        button.setMinimumHeight(dp(52));
        button.setPadding(dp(20), dp(12), dp(20), dp(12));
        button.setBackground(new RippleDrawable(ColorStateList.valueOf(0x227B9678),
            surface(primary ? GREEN : PAPER, 14, !primary), null));
        button.setOnClickListener(listener);
        return button;
    }
    private ImageView mark(int size) {
        ImageView image = new ImageView(this);
        image.setImageResource(R.mipmap.ic_launcher);
        image.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        image.setLayoutParams(new LinearLayout.LayoutParams(dp(size), dp(size)));
        return image;
    }

    private void showHome() {
        showingWorkspace = false;
        ((InputMethodManager) getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(root.getWindowToken(), 0);
        if (workspace != null) workspace.setVisibility(View.GONE);
        if (home != null) root.removeView(home);
        home = new ScrollView(this);
        home.setFillViewport(true);
        home.setClipToPadding(false);
        FrameLayout frame = new FrameLayout(this);
        home.addView(frame);
        LinearLayout content = column();
        int available = getResources().getConfiguration().screenWidthDp;
        boolean wide = available >= 800;
        int side = available < 600 ? 22 : 40;
        FrameLayout.LayoutParams bounds = new FrameLayout.LayoutParams(dp(Math.min(1000, available - side * 2)), -2, Gravity.TOP | Gravity.CENTER_HORIZONTAL);
        bounds.topMargin = dp(26);
        bounds.bottomMargin = dp(24);
        frame.addView(content, bounds);

        LinearLayout masthead = row();
        masthead.addView(mark(48));
        LinearLayout brand = column();
        brand.setPadding(dp(12), 0, 0, 0);
        brand.addView(text("Galaxy", 23, INK, "sans-serif-medium"));
        TextView sub = text("W O R K S P A C E", 10, MUTED, "sans-serif-medium");
        sub.setPadding(0, dp(4), 0, 0);
        brand.addView(sub);
        weighted(masthead, brand);
        if (available > 500) masthead.addView(text("YOUR TABLET. YOUR IDEAS.", 11, MUTED, "sans-serif-medium"));
        content.addView(masthead);
        gap(content, 24);

        LinearLayout hero = row();
        hero.setPadding(dp(wide ? 34 : 25), dp(28), dp(wide ? 34 : 25), dp(28));
        hero.setBackground(surface(INK, 28, false));
        LinearLayout message = column();
        TextView eyebrow = text("A LITTLE SPACE TO THINK BIG", 11, SAGE, "sans-serif-medium");
        eyebrow.setLetterSpacing(0.10f);
        message.addView(eyebrow);
        gap(message, 17);
        message.addView(text("Good ideas.\nA clear next step.", wide ? 43 : 34, PAPER, "sans-serif-medium"));
        gap(message, 16);
        message.addView(text("Bring your files, questions and unfinished thoughts.\nPick up right where you left off.", 16, Color.rgb(196, 204, 202), "sans-serif"));
        gap(message, 20);
        message.addView(text("EXPLORE   /   DISCUSS   /   REFINE", 11, SAGE, "sans-serif-medium"));
        weighted(hero, message);
        if (wide) {
            ImageView emblem = new ImageView(this);
            emblem.setImageResource(R.drawable.ic_galaxy_foreground);
            emblem.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            hero.addView(emblem, new LinearLayout.LayoutParams(dp(205), dp(205)));
        }
        content.addView(hero);
        gap(content, 18);

        LinearLayout connection = column();
        connection.setPadding(dp(24), dp(20), dp(24), dp(22));
        connection.setBackground(surface(Color.WHITE, 22, true));
        LinearLayout heading = row();
        weighted(heading, text(preferences.getBoolean("localEngine", false) ? "ON THIS TABLET" : "YOUR WORKSTATION", 11, MUTED, "sans-serif-medium"));
        Button settings = button("Connection", false, v -> connectionSettings());
        heading.addView(settings);
        connection.addView(heading);
        gap(connection, 10);
        connectionState = text("Checking connection…", 23, INK, "sans-serif-medium");
        connectionState.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        connection.addView(connectionState);
        gap(connection, 7);
        connectionHint = text("Looking for your workspace.", 14, MUTED, "sans-serif");
        connection.addView(connectionHint);
        gap(connection, 20);
        LinearLayout actions = wide ? row() : column();
        Button open = button("Open workspace  →", true, v -> openWorkspace());
        if (wide) weighted(actions, open); else actions.addView(open, new LinearLayout.LayoutParams(-1, -2));
        View spacer = new View(this);
        actions.addView(spacer, new LinearLayout.LayoutParams(dp(wide ? 12 : 1), dp(wide ? 1 : 10)));
        checkButton = button("Check connection", false, v -> checkConnection());
        actions.addView(checkButton, new LinearLayout.LayoutParams(wide ? -2 : -1, -2));
        connection.addView(actions);
        if (preferences.contains("savedDocument")) {
            gap(connection, 10);
            connection.addView(button("Last saved file: " + preferences.getString("savedName", "Document"), false, v -> {
                Uri saved = Uri.parse(preferences.getString("savedDocument", ""));
                showSavedFile(saved, preferences.getString("savedType", "application/octet-stream"), preferences.getString("savedName", "Document"));
            }));
        }
        content.addView(connection);
        gap(content, 17);
        LinearLayout footer = wide ? row() : column();
        TextView note = text(preferences.getBoolean("localEngine", false) ? "Your workspace lives here.\nConnect to the internet for AI replies." : "Your computer does the heavy lifting.\nYour tablet keeps it close.", 13, MUTED, "sans-serif");
        if (wide) weighted(footer, note); else footer.addView(note);
        if (!wide) gap(footer, 16);
        footer.addView(button("Add home screen icon", false, v -> pinShortcut()));
        content.addView(footer);
        root.addView(home, new LinearLayout.LayoutParams(-1, 0, 1));
        // onResume performs the first probe; subsequent native-home visits probe once here.
        if (!firstHome) checkConnection();
        firstHome = false;
    }

    private void startLocalEngine() {
        if (checkSelfPermission("com.termux.permission.RUN_COMMAND") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"com.termux.permission.RUN_COMMAND"}, 43);
            return;
        }
        try {
            Intent command = new Intent("com.termux.RUN_COMMAND");
            command.setClassName("com.termux", "com.termux.app.RunCommandService");
            command.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash");
            command.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[]{"/data/data/com.termux/files/home/galaxy-workspace/scripts/tablet-engine.sh"});
            command.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home/galaxy-workspace");
            command.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
            command.putExtra("com.termux.RUN_COMMAND_COMMAND_LABEL", "Galaxy local engine");
            startService(command);
            ui.postDelayed(this::checkConnection, 1800);
            ui.postDelayed(this::checkConnection, 4500);
        } catch (Exception ignored) {
            Toast.makeText(this, "Install and set up the Galaxy local engine first.", Toast.LENGTH_LONG).show();
        }
    }
    private void reconnectTablet() {
        if (!origin.equals(WorkspaceAddress.USB) || !preferences.getBoolean("localEngine", false) || pairingResult != null) return;
        if (connectionDialog != null) connectionDialog.dismiss();
        startLocalEngine();
        if (checkSelfPermission("com.termux.permission.RUN_COMMAND") != android.content.pm.PackageManager.PERMISSION_GRANTED) return;
        pairingAction = getPackageName() + ".PAIR." + java.util.UUID.randomUUID();
        Intent result = new Intent(this, PairResultReceiver.class).setAction(pairingAction);
        pairingResult = PendingIntent.getBroadcast(this, 0, result, PendingIntent.FLAG_ONE_SHOT | PendingIntent.FLAG_MUTABLE);
        Intent command = new Intent("com.termux.RUN_COMMAND").setClassName("com.termux", "com.termux.app.RunCommandService");
        command.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/bash");
        command.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[]{"/data/data/com.termux/files/home/galaxy-workspace/scripts/tablet-engine.sh", "--pair"});
        command.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home/galaxy-workspace");
        command.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
        command.putExtra("com.termux.RUN_COMMAND_BACKGROUND_CUSTOM_LOG_LEVEL", "0");
        command.putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", pairingResult);
        try {
            startService(command);
            Toast.makeText(this, "Reconnecting this tablet…", Toast.LENGTH_SHORT).show();
            ui.postDelayed(() -> {
                if (pairingResult != null) {
                    pairingResult.cancel(); pairingResult = null; pairingAction = null;
                    Toast.makeText(this, "Recovery timed out. Try Reconnect this tablet again.", Toast.LENGTH_LONG).show();
                }
            }, 60000);
        } catch (Exception ignored) {
            pairingResult.cancel(); pairingResult = null; pairingAction = null;
            Toast.makeText(this, "The local engine could not reconnect. Check its Termux permission.", Toast.LENGTH_LONG).show();
        }
    }
    public static final class PairResultReceiver extends BroadcastReceiver {
        @Override public void onReceive(Context context, Intent intent) {
            MainActivity activity = active.get();
            if (activity == null || activity.isDestroyed() || activity.pairingAction == null || !activity.pairingAction.equals(intent.getAction())) return;
            activity.pairingResult = null; activity.pairingAction = null;
            Bundle result = intent.getBundleExtra("result");
            String ticket = result == null ? "" : result.getString("stdout", "").trim();
            if (result == null || result.getInt("exitCode", -1) != 0 || !ticket.matches("[A-Za-z0-9_-]{43}")) {
                Toast.makeText(activity, "Local recovery could not finish. Try again from Connection.", Toast.LENGTH_LONG).show(); return;
            }
            activity.finishPairing(ticket);
        }
    }
    private void finishPairing(String ticket) {
        if (!origin.equals(WorkspaceAddress.USB) || !preferences.getBoolean("localEngine", false)) return;
        network.execute(() -> {
            String cookie = null;
            HttpURLConnection request = null;
            try {
                if (!waitForLocalEngine()) throw new java.io.IOException();
                request = (HttpURLConnection) new URL(WorkspaceAddress.USB + "/api/session/native").openConnection();
                request.setConnectTimeout(5000); request.setReadTimeout(5000); request.setInstanceFollowRedirects(false);
                request.setRequestMethod("POST"); request.setDoOutput(true);
                request.setRequestProperty("Content-Type", "application/json"); request.setRequestProperty("Origin", WorkspaceAddress.USB); request.setRequestProperty("X-Galaxy-Request", "1");
                try (java.io.OutputStream output = request.getOutputStream()) { output.write(new JSONObject().put("ticket", ticket).toString().getBytes(StandardCharsets.UTF_8)); }
                if (request.getResponseCode() == 200) cookie = request.getHeaderField("Set-Cookie");
            } catch (Exception ignored) { }
            finally { if (request != null) request.disconnect(); }
            String sessionCookie = cookie;
            ui.post(() -> {
                if (isDestroyed() || !origin.equals(WorkspaceAddress.USB) || !preferences.getBoolean("localEngine", false)) return;
                if (sessionCookie == null) { Toast.makeText(this, "The engine is not ready yet. Try Reconnect this tablet again.", Toast.LENGTH_LONG).show(); return; }
                CookieManager.getInstance().setCookie(origin, sessionCookie, ok -> {
                    CookieManager.getInstance().flush();
                    if (browser != null) browser.reload();
                    openWorkspace();
                });
            });
        });
    }
    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == 43 && results.length > 0 && results[0] == android.content.pm.PackageManager.PERMISSION_GRANTED) startLocalEngine();
    }
    private void checkConnection() {
        if (checkButton == null || isDestroyed()) return;
        int generation = healthGeneration.incrementAndGet();
        String checkedOrigin = origin;
        connectionState.setText(R.string.checking_connection);
        checkButton.setEnabled(false);
        network.execute(() -> {
            boolean reachable = false;
            boolean tabletRuntime = false;
            HttpURLConnection request = null;
            try {
                request = (HttpURLConnection) new URL(checkedOrigin + "/api/session").openConnection();
                request.setConnectTimeout(4000);
                request.setReadTimeout(4000);
                request.setInstanceFollowRedirects(false);
                request.setUseCaches(false);
                if (request.getResponseCode() == 200) {
                    byte[] bytes = request.getInputStream().readNBytes(2048);
                    JSONObject status = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
                    tabletRuntime = "tablet".equals(status.optString("runtime"));
                    reachable = status.opt("authenticated") instanceof Boolean;
                    if (preferences.getBoolean("localEngine", false) && !tabletRuntime) reachable = false;
                }
            } catch (Exception ignored) {
                // Never log a response, URL with a token, or a pairing credential.
            } finally { if (request != null) request.disconnect(); }
            boolean connected = reachable;
            boolean onTablet = tabletRuntime;
            ui.post(() -> {
                if (isDestroyed() || generation != healthGeneration.get()) return;
                checkButton.setEnabled(true);
                connectionState.setText(connected ? "Ready when you are" : "Let’s reconnect");
                connectionState.setTextColor(connected ? GREEN : INK);
                boolean usb = origin.equals(WorkspaceAddress.USB);
                connectionHint.setText(preferences.getBoolean("localEngine", false)
                    ? (connected && onTablet ? "Running on this tablet · No computer needed." : "Tap Open workspace to start the engine on this tablet. Internet is needed for AI replies.")
                    : connected
                    ? (usb ? "Connected through USB · Keep your computer awake." : "Your workstation is reachable · Ready to open.")
                    : (usb ? "Keep the USB cable connected and the workspace running on your computer." : "Check your private network and make sure your computer is awake."));
            });
        });
    }

    private void connectionSettings() {
        LinearLayout form = column();
        form.setPadding(dp(24), dp(12), dp(24), dp(8));
        form.addView(text("Workspace address", 14, INK, "sans-serif-medium"));
        gap(form, 10);
        EditText address = new EditText(this);
        address.setText(origin);
        address.setTextSize(16);
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setSingleLine(true);
        address.setSelectAllOnFocus(true);
        address.setContentDescription("Workstation address");
        form.addView(address, new LinearLayout.LayoutParams(-1, -2));
        gap(form, 16);
        form.addView(text("Use this tablet starts its installed local engine. No computer or VPN is needed. An HTTPS address can connect to a separately configured workstation.", 14, MUTED, "sans-serif"));
        if (preferences.getBoolean("localEngine", false) && origin.equals(WorkspaceAddress.USB)) {
            gap(form, 12);
            form.addView(button("Reconnect this tablet", false, v -> reconnectTablet()));
        }
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Your connection").setView(form)
            .setNegativeButton("Cancel", null).setNeutralButton("Use this tablet", null).setPositiveButton("Save", null).create();
        connectionDialog = dialog;
        dialog.setOnShowListener(ignored -> {
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v -> {
                origin = WorkspaceAddress.USB;
                preferences.edit().putString("origin", origin).putBoolean("localEngine", true).remove("lastUrl").apply();
                destroyWorkspace(); dialog.dismiss(); showHome(); startLocalEngine();
            });
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                try {
                    String next = WorkspaceAddress.normalize(address.getText().toString());
                    if (!next.equals(WorkspaceAddress.USB)) preferences.edit().putBoolean("localEngine", false).apply();
                    if (!next.equals(origin)) {
                        origin = next;
                        preferences.edit().putString("origin", origin).remove("lastUrl").apply();
                        destroyWorkspace();
                    }
                    dialog.dismiss();
                    showHome();
                } catch (IllegalArgumentException e) { address.setError(e.getMessage()); }
            });
        });
        dialog.show();
    }

    private void pinShortcut() {
        ShortcutManager shortcuts = getSystemService(ShortcutManager.class);
        if (shortcuts == null || !shortcuts.isRequestPinShortcutSupported()) {
            Toast.makeText(this, "Find Galaxy Workspace in your app drawer and drag it to your home screen.", Toast.LENGTH_LONG).show();
            return;
        }
        ShortcutInfo shortcut = new ShortcutInfo.Builder(this, "galaxy-workspace")
            .setShortLabel("Galaxy Workspace").setLongLabel("Galaxy Workspace")
            .setIcon(Icon.createWithResource(this, R.mipmap.ic_launcher))
            .setIntent(new Intent(this, MainActivity.class).setAction(Intent.ACTION_MAIN)
                .addCategory(Intent.CATEGORY_LAUNCHER).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED))
            .build();
        shortcuts.requestPinShortcut(shortcut, null);
    }

    private void openWorkspace() {
        if (preferences.getBoolean("localEngine", false)) startLocalEngine();
        showingWorkspace = true;
        home.setVisibility(View.GONE);
        if (workspace == null) createWorkspace();
        else if (loadFailed) loadWorkspaceUrl(preferences.getString("lastUrl", origin));
        workspace.setVisibility(View.VISIBLE);
    }

    @SuppressLint("SetJavaScriptEnabled") // The controlled React workspace requires JS; no native bridge is exposed.
    private void createWorkspace() {
        workspace = column();
        LinearLayout toolbar = row();
        toolbar.setPadding(dp(12), dp(4), dp(12), dp(4));
        Button back = button("‹  Home", false, v -> showHome());
        toolbar.addView(back);
        TextView title = text("Galaxy Workspace", 15, INK, "sans-serif-medium");
        title.setGravity(Gravity.CENTER);
        weighted(toolbar, title);
        TextView mode = text(preferences.getBoolean("localEngine", false) ? "ON DEVICE" : origin.equals(WorkspaceAddress.USB) ? "USB" : "HTTPS", 11, GREEN, "sans-serif-medium");
        mode.setPadding(dp(18), 0, dp(10), 0);
        toolbar.addView(mode);
        workspace.addView(toolbar);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setProgressTintList(ColorStateList.valueOf(GREEN));
        workspace.addView(progress, new LinearLayout.LayoutParams(-1, dp(2)));
        webArea = new FrameLayout(this);
        workspace.addView(webArea, new LinearLayout.LayoutParams(-1, 0, 1));
        browser = new WebView(this);
        browser.setBackgroundColor(PAPER);
        browser.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        WebSettings settings = browser.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSafeBrowsingEnabled(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(true);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setGeolocationEnabled(false);
        settings.setUserAgentString(settings.getUserAgentString() + " GalaxyWorkspace/" + BuildConfig.VERSION_NAME);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(browser, false);
        browser.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (WorkspaceAddress.contains(origin, url)) return false;
                if (request.isForMainFrame() && request.hasGesture()) openExternal(url);
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (WorkspaceAddress.contains(origin, request.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", java.util.Map.of(), new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                loadFailed = false;
                if (errorCard != null) errorCard.setVisibility(View.GONE);
                progress.setVisibility(View.VISIBLE);
            }
            @Override public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.INVISIBLE);
                if (!loadFailed) rememberUrl(url);
                CookieManager.getInstance().flush();
            }
            @Override public void doUpdateVisitedHistory(WebView view, String url, boolean reload) { rememberUrl(url); }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showConnectionError("Your workspace is out of reach", preferences.getBoolean("localEngine", false) ? "Return Home and open the workspace again to start its local engine. Saved files remain on this tablet." : "Keep your computer awake and the USB cable or private network connected. Your saved conversations stay on your computer.");
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame()) showConnectionError("The workspace could not open", "Check that the app’s connection address matches the workspace address on your computer.");
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                showConnectionError("This connection could not be verified", "Check the workstation’s HTTPS address and certificate, then try again.");
            }
            @Override public boolean onRenderProcessGone(WebView view, android.webkit.RenderProcessGoneDetail detail) {
                destroyWorkspace();
                showHome();
                Toast.makeText(MainActivity.this, "The workspace view closed. Open it again to continue your saved conversation.", Toast.LENGTH_LONG).show();
                return true;
            }
        });
        browser.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (!WorkspaceAddress.contains(origin, view.getUrl())) return false;
                if (fileSelection != null) fileSelection.onReceiveValue(null);
                fileSelection = callback;
                selectionOrigin = origin;
                Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
                picker.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try { startActivityForResult(picker, PICK_FILES); }
                catch (ActivityNotFoundException ignored) { fileSelection.onReceiveValue(null); fileSelection = null; }
                return true;
            }
            @Override public void onProgressChanged(WebView view, int value) { progress.setProgress(value); }
            @Override public void onPermissionRequest(PermissionRequest request) { request.deny(); }
            @Override public boolean onCreateWindow(WebView view, boolean dialog, boolean userGesture, Message resultMsg) {
                if (!userGesture) return false;
                WebView popup = new WebView(MainActivity.this);
                popups.add(popup);
                popup.setWebViewClient(new WebViewClient() {
                    @Override public boolean shouldOverrideUrlLoading(WebView unused, WebResourceRequest request) {
                        openExternal(request.getUrl().toString());
                        return true;
                    }
                });
                ((WebView.WebViewTransport) resultMsg.obj).setWebView(popup);
                resultMsg.sendToTarget();
                ui.postDelayed(() -> { if (popups.remove(popup)) { popup.stopLoading(); popup.destroy(); } }, 3000);
                return true;
            }
        });
        browser.setDownloadListener((url, userAgent, disposition, mime, length) -> downloadReport(url, disposition, mime));
        webArea.addView(browser, new FrameLayout.LayoutParams(-1, -1));
        root.addView(workspace, new LinearLayout.LayoutParams(-1, 0, 1));
        String saved = preferences.getString("lastUrl", origin);
        loadWorkspaceUrl(saved);
    }

    private boolean waitForLocalEngine() {
        for (int attempt = 0; attempt < 12 && !Thread.currentThread().isInterrupted(); attempt++) {
            HttpURLConnection request = null;
            try {
                request = (HttpURLConnection) new URL(WorkspaceAddress.USB + "/api/session").openConnection();
                request.setConnectTimeout(700); request.setReadTimeout(700); request.setInstanceFollowRedirects(false); request.setUseCaches(false);
                if (request.getResponseCode() == 200) {
                    JSONObject result = new JSONObject(new String(request.getInputStream().readNBytes(2048), StandardCharsets.UTF_8));
                    if ("tablet".equals(result.optString("runtime")) && result.opt("authenticated") instanceof Boolean) return true;
                }
            } catch (Exception ignored) { }
            finally { if (request != null) request.disconnect(); }
            try { Thread.sleep(250); } catch (InterruptedException ignored) { Thread.currentThread().interrupt(); return false; }
        }
        return false;
    }
    private void loadWorkspaceUrl(String saved) {
        String target = WorkspaceAddress.contains(origin, saved) ? saved : origin;
        if (!preferences.getBoolean("localEngine", false) || !origin.equals(WorkspaceAddress.USB)) { browser.loadUrl(target); return; }
        WebView expected = browser;
        progress.setIndeterminate(true); progress.setVisibility(View.VISIBLE);
        network.execute(() -> {
            boolean ready = waitForLocalEngine();
            ui.post(() -> {
                if (isDestroyed() || browser != expected) return;
                progress.setIndeterminate(false);
                if (ready) browser.loadUrl(target);
                else showConnectionError("The local engine is still starting", "Tap Reconnect to try again. Your saved work and unsent drafts remain on this tablet.");
            });
        });
    }

    private void rememberUrl(String url) {
        if (WorkspaceAddress.contains(origin, url)) {
            // Workspace state uses the fragment. Never retain query parameters or credentials.
            Uri parsed = Uri.parse(url);
            preferences.edit().putString("lastUrl", origin + (parsed.getEncodedFragment() == null ? "" : "/#" + parsed.getEncodedFragment())).apply();
        }
    }
    private void downloadReport(String url, String disposition, String mime) {
        String type = TransferPolicy.mime(mime);
        if (downloading || reportDownload != null || type == null || !TransferPolicy.documentUrl(origin, url)) {
            Toast.makeText(this, "Choose a supported document or report export in the workspace.", Toast.LENGTH_LONG).show();
            return;
        }
        String cookie = CookieManager.getInstance().getCookie(origin);
        String downloadOrigin = origin;
        String filename = TransferPolicy.filename(disposition, type);
        downloading = true;
        Toast.makeText(this, "Preparing document…", Toast.LENGTH_SHORT).show();
        network.execute(() -> {
            HttpURLConnection request = null;
            byte[] result = null;
            try {
                request = (HttpURLConnection) new URL(url).openConnection();
                request.setConnectTimeout(5000); request.setReadTimeout(15000);
                request.setInstanceFollowRedirects(false); request.setUseCaches(false);
                if (cookie != null) request.setRequestProperty("Cookie", cookie);
                if (request.getResponseCode() != 200 || !type.equals(TransferPolicy.mime(request.getContentType()))) throw new java.io.IOException();
                try (java.io.InputStream input = request.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                    byte[] buffer = new byte[8192]; int count;
                    long deadline = android.os.SystemClock.elapsedRealtime() + 30_000;
                    while ((count = input.read(buffer)) != -1) {
                        if (output.size() + count > 20_000_000 || android.os.SystemClock.elapsedRealtime() > deadline) throw new java.io.IOException();
                        output.write(buffer, 0, count);
                    }
                    result = output.toByteArray();
                }
            } catch (Exception ignored) { /* No response contents or credentials in logs. */ }
            finally { if (request != null) request.disconnect(); }
            byte[] bytes = result;
            ui.post(() -> {
                downloading = false;
                if (isDestroyed() || !origin.equals(downloadOrigin)) return;
                if (bytes == null || bytes.length == 0) { Toast.makeText(this, "Download failed. Reconnect and try the saved export again.", Toast.LENGTH_LONG).show(); return; }
                reportDownload = bytes; downloadName = filename; downloadType = type; downloadUrl = url;
                new AlertDialog.Builder(this).setTitle(filename)
                    .setItems(new String[]{"Open in app", "Save a copy", "Share a copy"}, (dialog, which) -> {
                        if (which == 1) saveDocument(); else prepareAppCopy(which == 2);
                    }).setOnCancelListener(dialog -> reportDownload = null).show();
            });
        });
    }
    private void saveDocument() {
        Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(downloadType).putExtra(Intent.EXTRA_TITLE, downloadName);
        save.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try { startActivityForResult(save, SAVE_REPORT); }
        catch (ActivityNotFoundException ignored) { reportDownload = null; Toast.makeText(this, "No file picker is available.", Toast.LENGTH_LONG).show(); }
    }
    private void prepareAppCopy(boolean share) {
        byte[] bytes = reportDownload; reportDownload = null;
        String name = downloadName, type = downloadType;
        if (bytes == null) return;
        network.execute(() -> {
            Uri uri = null;
            try {
                File parent = new File(getFilesDir(), "transfers");
                parent.mkdirs();
                File[] old = parent.listFiles();
                if (old != null) for (File directory : old) {
                    if (directory.lastModified() < System.currentTimeMillis() - 7L * 24 * 60 * 60 * 1000) {
                        File[] files = directory.listFiles(); if (files != null) for (File file : files) file.delete();
                        directory.delete();
                    }
                }
                old = parent.listFiles();
                if (old != null && old.length >= 20) throw new java.io.IOException("Transfer limit");
                File folder = new File(parent, java.util.UUID.randomUUID().toString());
                if (!folder.mkdir()) throw new java.io.IOException();
                File file = new File(folder, name);
                try (FileOutputStream output = new FileOutputStream(file)) { output.write(bytes); }
                uri = FileProvider.getUriForFile(this, getPackageName() + ".transfers", file);
            } catch (Exception ignored) { }
            Uri copy = uri;
            ui.post(() -> {
                if (isDestroyed()) return;
                if (copy == null) { Toast.makeText(this, "Could not prepare an app copy. Use Save a copy instead.", Toast.LENGTH_LONG).show(); return; }
                handoff(copy, type, name, share);
            });
        });
    }
    private void handoff(Uri uri, String type, String name, boolean share) {
        Intent intent = new Intent(share ? Intent.ACTION_SEND : Intent.ACTION_VIEW);
        if (share) { intent.setType(type); intent.putExtra(Intent.EXTRA_STREAM, uri); intent.putExtra(Intent.EXTRA_SUBJECT, name); }
        else intent.setDataAndType(uri, type);
        intent.setClipData(ClipData.newRawUri(name, uri));
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivity(Intent.createChooser(intent, share ? "Share a copy" : "Open document"));
            if (!share) Toast.makeText(this, "To edit, save your own copy in the Office app. Bring it back with Add material.", Toast.LENGTH_LONG).show();
        } catch (ActivityNotFoundException | SecurityException ignored) { Toast.makeText(this, "No app could open this file. Save a copy and open it from My Files.", Toast.LENGTH_LONG).show(); }
    }
    private void showSavedFile(Uri uri, String type, String name) {
        new AlertDialog.Builder(this).setTitle("Saved: " + name).setMessage("The file was written to your selected location. Open it or share a copy; sharing does not send automatically.")
            .setPositiveButton("Open", (d, w) -> handoff(uri, type, name, false))
            .setNeutralButton("Share", (d, w) -> handoff(uri, type, name, true))
            .setNegativeButton("Done", null).show();
    }
    private void recordDeviceSave(String url, String savedOrigin, Uri destination, String name) {
        if (!origin.equals(savedOrigin) || !TransferPolicy.exportUrl(savedOrigin, url)) return;
        String cookie = CookieManager.getInstance().getCookie(savedOrigin);
        String location = destination.getAuthority();
        try {
            String id = android.provider.DocumentsContract.getDocumentId(destination);
            if (id.startsWith("primary:")) location = id.substring(8);
        } catch (Exception ignored) { }
        String receiptLocation = location + " / " + name;
        network.execute(() -> {
            HttpURLConnection request = null;
            boolean recorded = false;
            try {
                request = (HttpURLConnection) new URL(url.substring(0, url.length() - "download".length()) + "device-receipt").openConnection();
                request.setConnectTimeout(5000); request.setReadTimeout(5000); request.setInstanceFollowRedirects(false);
                request.setRequestMethod("POST"); request.setDoOutput(true);
                request.setRequestProperty("Content-Type", "application/json"); request.setRequestProperty("Origin", savedOrigin); request.setRequestProperty("X-Galaxy-Request", "1");
                if (cookie != null) request.setRequestProperty("Cookie", cookie);
                try (java.io.OutputStream output = request.getOutputStream()) { output.write(new JSONObject().put("destination", receiptLocation).toString().getBytes(StandardCharsets.UTF_8)); }
                recorded = request.getResponseCode() == 200;
            } catch (Exception ignored) { }
            finally { if (request != null) request.disconnect(); }
            boolean complete = recorded;
            ui.post(() -> {
                if (isDestroyed()) return;
                if (complete && browser != null && origin.equals(savedOrigin)) browser.reload();
                else if (!complete) Toast.makeText(this, "File saved. Its export-history receipt could not be recorded; Last saved file remains available from Home.", Toast.LENGTH_LONG).show();
            });
        });
    }
    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_FILES) {
            ValueCallback<Uri[]> callback = fileSelection; fileSelection = null;
            if (callback == null) return;
            java.util.List<Uri> selected = new java.util.ArrayList<>();
            if (resultCode == RESULT_OK && data != null && origin.equals(selectionOrigin)) {
                if (data.getClipData() != null) {
                    for (int i = 0; i < data.getClipData().getItemCount() && i < 50; i++) selected.add(data.getClipData().getItemAt(i).getUri());
                } else if (data.getData() != null) selected.add(data.getData());
            }
            selected.removeIf(uri -> !TransferPolicy.selectedContent(uri.toString(), getPackageName()));
            callback.onReceiveValue(selected.isEmpty() ? null : selected.toArray(new Uri[0]));
        } else if (requestCode == SAVE_REPORT) {
            byte[] bytes = reportDownload; reportDownload = null;
            String type = downloadType, savedUrl = downloadUrl, savedOrigin = origin;
            Uri destination = data == null ? null : data.getData();
            if (resultCode != RESULT_OK || bytes == null || destination == null || !TransferPolicy.selectedContent(destination.toString(), getPackageName())) return;
            String selectedName = downloadName;
            try (android.database.Cursor cursor = getContentResolver().query(destination, new String[]{android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                if (cursor != null && cursor.moveToFirst() && !cursor.isNull(0)) selectedName = cursor.getString(0).substring(0, Math.min(240, cursor.getString(0).length()));
            } catch (Exception ignored) { }
            String name = selectedName;
            try {
                if ((data.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION) != 0)
                    getContentResolver().takePersistableUriPermission(destination, Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } catch (SecurityException ignored) { }
            network.execute(() -> {
                boolean saved = false;
                try (java.io.OutputStream output = getContentResolver().openOutputStream(destination, "wt")) {
                    if (output != null) { output.write(bytes); output.flush(); saved = true; }
                } catch (Exception ignored) { saved = false; }
                boolean success = saved;
                if (success) preferences.edit().putString("savedDocument", destination.toString()).putString("savedName", name).putString("savedType", type).apply();
                ui.post(() -> {
                    if (!isDestroyed()) {
                        if (success) { recordDeviceSave(savedUrl, savedOrigin, destination, name); showSavedFile(destination, type, name); }
                        else Toast.makeText(this, "Could not confirm the save. Check the selected folder before saving again.", Toast.LENGTH_LONG).show();
                    }
                });
            });
        }
    }
    private void openExternal(String url) {
        if (!WorkspaceAddress.externalWebLink(url)) {
            Toast.makeText(this, "This link cannot be opened from the workspace.", Toast.LENGTH_SHORT).show();
            return;
        }
        try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)).addCategory(Intent.CATEGORY_BROWSABLE)); }
        catch (ActivityNotFoundException ignored) { Toast.makeText(this, "No browser is available to open this link.", Toast.LENGTH_SHORT).show(); }
    }
    private void showConnectionError(String title, String detail) {
        loadFailed = true;
        progress.setVisibility(View.INVISIBLE);
        if (errorCard != null) webArea.removeView(errorCard);
        errorCard = column();
        errorCard.setGravity(Gravity.CENTER);
        errorCard.setPadding(dp(32), dp(24), dp(32), dp(24));
        errorCard.setBackgroundColor(PAPER);
        errorCard.addView(mark(84));
        gap(errorCard, 24);
        TextView heading = text(title, 26, INK, "sans-serif-medium");
        heading.setGravity(Gravity.CENTER);
        errorCard.addView(heading);
        gap(errorCard, 14);
        TextView explanation = text(detail, 16, MUTED, "sans-serif");
        explanation.setGravity(Gravity.CENTER);
        explanation.setMaxWidth(dp(550));
        errorCard.addView(explanation);
        gap(errorCard, 24);
        errorCard.addView(button("Reconnect", true, v -> {
            if (preferences.getBoolean("localEngine", false)) startLocalEngine();
            errorCard.setVisibility(View.GONE);
            String saved = preferences.getString("lastUrl", origin);
            loadWorkspaceUrl(saved);
        }));
        webArea.addView(errorCard, new FrameLayout.LayoutParams(-1, -1));
    }
    private void navigateBack() {
        if (showingWorkspace) {
            if (!loadFailed && browser != null && browser.canGoBack()) browser.goBack();
            else showHome();
        } else moveTaskToBack(true);
    }
    @Override public void onConfigurationChanged(Configuration config) {
        super.onConfigurationChanged(config);
        if (!showingWorkspace) showHome();
    }
    @Override protected void onResume() {
        super.onResume();
        if (browser != null) browser.onResume();
        if (!showingWorkspace) checkConnection();
    }
    @Override protected void onPause() {
        if (browser != null) browser.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBoolean("workspace", showingWorkspace);
        super.onSaveInstanceState(state);
    }
    private void destroyWorkspace() {
        if (fileSelection != null) { fileSelection.onReceiveValue(null); fileSelection = null; }
        reportDownload = null;
        for (WebView popup : popups) { popup.stopLoading(); popup.destroy(); }
        popups.clear();
        if (browser != null) {
            browser.stopLoading();
            webArea.removeView(browser);
            browser.destroy();
            browser = null;
        }
        if (workspace != null) root.removeView(workspace);
        workspace = null;
        errorCard = null;
    }
    @Override protected void onDestroy() {
        if (pairingResult != null) pairingResult.cancel();
        healthGeneration.incrementAndGet();
        network.shutdownNow();
        ui.removeCallbacksAndMessages(null);
        destroyWorkspace();
        super.onDestroy();
    }
}
