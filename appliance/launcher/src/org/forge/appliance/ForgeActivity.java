package org.forge.appliance;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.graphics.Typeface;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.ScrollView;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.regex.Pattern;

/** A small local-only controller for the Forge appliance broker. */
public final class ForgeActivity extends Activity {
    private static final String SOCKET = "forge.appliance.v1";
    private static final int MAX_REPLY = 512;
    private static final int TIMEOUT_MS = 2000;
    private static final String PREFS = "forge";
    private static final String HOME_URL = "home_url";
    private static final Pattern HOME = Pattern.compile("https?://[^\\s/@?#]+(?::[0-9]{1,5})?(?:/[^\\s?#]*)?", Pattern.CASE_INSENSITIVE);
    private static final int GREEN = Color.rgb(203, 237, 156);
    private static final int DARK = Color.rgb(16, 25, 24);

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private ScheduledThreadPoolExecutor executor;
    private ScheduledFuture<?> statusPoll;
    private TextView status;
    private TextView message;
    private EditText homeUrl;
    private Button start;
    private Button recover;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(buildView());
        homeUrl.setText(getSharedPreferences(PREFS, MODE_PRIVATE).getString(HOME_URL, ""));
    }

    private View buildView() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setGravity(Gravity.CENTER_HORIZONTAL);
        page.setPadding(dp(24), dp(28), dp(24), dp(20));
        page.setBackgroundColor(DARK);
        TextView title = text("FORGE", 34, GREEN); page.addView(title);
        page.addView(text("Music + Home appliance", 18, Color.WHITE));
        status = text("Checking appliance…", 16, GREEN); page.addView(status);
        message = text("", 14, Color.LTGRAY); page.addView(message);
        start = button("START FORGE"); start.setOnClickListener(v -> sendStart()); page.addView(start);
        recover = button("RECOVER ANDROID"); recover.setVisibility(View.GONE); recover.setOnClickListener(v -> send("STOP\n", "Recovering Android…")); page.addView(recover);
        page.addView(text("Optional Home Assistant URL", 15, Color.WHITE));
        homeUrl = new EditText(this);
        homeUrl.setTextColor(Color.WHITE); homeUrl.setHintTextColor(Color.GRAY); homeUrl.setHint("https://home.example");
        homeUrl.setSingleLine(true); homeUrl.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        page.addView(homeUrl, new LinearLayout.LayoutParams(-1, -2));
        Button save = button("SAVE HOME URL"); save.setOnClickListener(v -> saveHome()); page.addView(save);
        Button settings = button("WI-FI & ANDROID SETTINGS");
        settings.setOnClickListener(v -> startActivity(new Intent(android.provider.Settings.ACTION_SETTINGS)));
        page.addView(settings);
        page.addView(text("Music: use Browse in Forge. Return to Android via Home.", 13, Color.LTGRAY));
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.addView(page);
        return scroll;
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTypeface(Typeface.MONOSPACE); view.setTextSize(size); view.setTextColor(color);
        view.setGravity(Gravity.CENTER); view.setPadding(0, dp(7), 0, dp(7)); return view;
    }
    private Button button(String value) {
        Button view = new Button(this); view.setText(value); view.setTypeface(Typeface.MONOSPACE); view.setTextColor(DARK); view.setTextSize(17); view.setBackgroundColor(GREEN);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.setMargins(0, dp(8), 0, dp(8)); view.setLayoutParams(p); return view;
    }
    private int dp(int value) { return (int) (value * getResources().getDisplayMetrics().density + .5f); }

    @Override protected void onResume() { super.onResume(); startExecutor(); pollStatus(); }
    @Override protected void onPause() { super.onPause(); stopExecutor(); }

    private void startExecutor() {
        if (executor == null || executor.isShutdown()) executor = new ScheduledThreadPoolExecutor(1);
    }
    private void stopExecutor() {
        if (statusPoll != null) { statusPoll.cancel(true); statusPoll = null; }
        if (executor != null) { executor.shutdownNow(); executor = null; }
    }
    private void pollStatus() {
        if (executor == null) return;
        statusPoll = executor.scheduleWithFixedDelay(() -> command("STATUS\n", true), 0, 2, java.util.concurrent.TimeUnit.SECONDS);
    }
    private void sendStart() { send("START\n", "Starting Forge…"); }
    private void send(String line, String optimistic) {
        message.setText(optimistic); start.setEnabled(false); if (executor != null) executor.execute(() -> command(line, false));
    }
    private void saveHome() {
        String value = homeUrl.getText().toString();
        if (!value.isEmpty() && !validHome(value)) { message.setText("Enter a plain http(s) URL without credentials, query, or fragment."); return; }
        String command = value.isEmpty() ? "HOME -\n" : "HOME " + value + "\n";
        if (executor != null) executor.execute(() -> {
            String reply = request(command);
            runOnUiThread(() -> {
                if (reply.startsWith("OK SAVED")) { getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(HOME_URL, value).apply(); message.setText("Home URL saved for the next Forge session."); }
                else message.setText(userMessage(reply));
            });
        });
    }
    private void command(String line, boolean quiet) {
        String reply = request(line);
        runOnUiThread(() -> {
            if (isFinishing()) return;
            if (reply.startsWith("OK ")) { status.setText(stateMessage(reply)); recover.setVisibility(reply.contains("FAILED") ? View.VISIBLE : View.GONE); if (!quiet) message.setText(stateMessage(reply)); }
            else { status.setText("Appliance unavailable"); recover.setVisibility(View.VISIBLE); if (!quiet || reply.startsWith("UNAVAILABLE")) message.setText(userMessage(reply)); }
            start.setEnabled(reply.startsWith("OK IDLE "));
        });
    }
    private String request(String command) {
        LocalSocket socket = new LocalSocket();
        Runnable deadline = () -> { try { socket.close(); } catch (IOException ignored) { } };
        mainHandler.postDelayed(deadline, TIMEOUT_MS);
        try {
            socket.connect(new LocalSocketAddress(SOCKET, LocalSocketAddress.Namespace.ABSTRACT));
            socket.setSoTimeout(TIMEOUT_MS);
            if (socket.getPeerCredentials().getUid() != 0) return "UNAVAILABLE";
            OutputStream out = socket.getOutputStream(); out.write(command.getBytes(StandardCharsets.US_ASCII)); out.flush();
            BufferedInputStream in = new BufferedInputStream(socket.getInputStream()); byte[] data = new byte[MAX_REPLY]; int count = 0, next;
            while (count < MAX_REPLY && (next = in.read()) != -1) { if (next == '\n') break; if (next < 0x20 || next > 0x7e) return "UNAVAILABLE"; data[count++] = (byte) next; }
            return count == MAX_REPLY ? "UNAVAILABLE" : new String(data, 0, count, StandardCharsets.US_ASCII);
        } catch (IOException ignored) { return "UNAVAILABLE"; }
        finally { mainHandler.removeCallbacks(deadline); try { socket.close(); } catch (IOException ignored) { } }
    }
    private String stateMessage(String reply) {
        if (reply.startsWith("OK IDLE ")) return "Ready when you are";
        if (reply.startsWith("OK STARTING ")) return "Opening your music…";
        if (reply.startsWith("OK RUNNING ")) return "Forge is running";
        if (reply.startsWith("OK STOPPING ") || reply.startsWith("OK RECOVERING ")) return "Returning to Android…";
        return "Recovery needs attention";
    }
    private String userMessage(String reply) {
        if (reply.startsWith("ERR BAD_URL")) return "That Home URL is not supported.";
        if (reply.startsWith("ERR BUSY")) return "Forge is busy; try again shortly.";
        return "Forge appliance setup is unavailable. Start is ready once its local service is installed.";
    }
    private static boolean validHome(String value) {
        if (value.length() > 256 || !HOME.matcher(value).matches()) return false;
        for (int i = 0; i < value.length(); i++) if (value.charAt(i) < 0x21 || value.charAt(i) > 0x7e) return false;
        return true;
    }
}
