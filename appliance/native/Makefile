CC ?= cc
BUILD_DIR ?= ../../output/native
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Werror -D_POSIX_C_SOURCE=200809L
LDFLAGS ?=

.PHONY: all host hardware clean
all: $(BUILD_DIR)/forge-engine $(BUILD_DIR)/forge-panel
host: all $(BUILD_DIR)/forge-panel-x11
hardware: all $(BUILD_DIR)/forge-pcm-sink $(BUILD_DIR)/forge-namespace-run $(BUILD_DIR)/forge-music-bridge $(BUILD_DIR)/forge-sessiond

$(BUILD_DIR):
	mkdir -p "$@"

$(BUILD_DIR)/forge-engine: engine.c core.c core.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) engine.c core.c $(LDFLAGS) -o "$@"

$(BUILD_DIR)/forge-panel: panel.c samsung_display.h browser_surface.h touch_state.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) panel.c $(LDFLAGS) -o "$@"

$(BUILD_DIR)/libforge-panel.so: panel.c samsung_display.h browser_surface.h touch_state.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) -DFORGE_ANDROID_SURFACE -fPIC -shared panel.c -landroid -Wl,--gc-sections -Wl,-z,relro,-z,now -o "$@"

$(BUILD_DIR)/forge-panel-x11: panel.c samsung_display.h browser_surface.h touch_state.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) -DFORGE_X11 panel.c $$(pkg-config --cflags --libs x11) $(LDFLAGS) -o "$@"

$(BUILD_DIR)/forge-pcm-sink: pcm_sink.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) pcm_sink.c $(LDFLAGS) -o "$@"

$(BUILD_DIR)/forge-namespace-run: namespace_run.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) namespace_run.c $(LDFLAGS) -o "$@"

$(BUILD_DIR)/forge-music-bridge: music_bridge.c bridge_json.h music_bridge_ui_maintenance.h music_bridge_queue_maintenance.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) -pthread music_bridge.c $(LDFLAGS) -o "$@"

$(BUILD_DIR)/forge-sessiond: sessiond.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) sessiond.c $(LDFLAGS) -o "$@"

clean:
	rm -f "$(BUILD_DIR)/forge-engine" "$(BUILD_DIR)/forge-panel" "$(BUILD_DIR)/forge-panel-x11"
	rm -f "$(BUILD_DIR)/forge-pcm-sink" "$(BUILD_DIR)/forge-namespace-run"
	rm -f "$(BUILD_DIR)/forge-music-bridge"
