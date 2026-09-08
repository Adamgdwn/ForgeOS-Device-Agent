"""Fake-command lifecycle coverage for the Android network handoff guard."""

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "appliance/device/forge-session.sh"


DISPATCHER = r'''#!/bin/sh
name=$(basename "$0")
log() { printf '%s\n' "$1" >> "$FORGE_FAKE_LOG"; }
state() { cat "$FORGE_FAKE_STATE/$1" 2>/dev/null || printf '%s\n' running; }
case "$name" in
  getprop)
    service=${1#init.svc.}
    if [ "$service" = netd ] && [ "${FAIL_NETD_STOP_WAIT-}" = 1 ] && [ -f "$FORGE_FAKE_STATE/netd_wait" ]; then
      printf '%s\n' stopping
    else
      state "$service"
    fi
    ;;
  stop)
    log "stop:$1"
    printf '%s\n' stopped > "$FORGE_FAKE_STATE/$1"
    [ "$1" = netd ] && : > "$FORGE_FAKE_STATE/netd_wait"
    :
    ;;
  start)
    log "start:$1"
    if [ "$1" = netd ] && [ "${FAIL_START_NETD-}" = 1 ]; then exit 1; fi
    printf '%s\n' running > "$FORGE_FAKE_STATE/$1"
    [ "$1" = netd ] && : > "$FORGE_FAKE_STATE/netd_restarted"
    :
    ;;
  ip)
    log "ip:$*"
    if [ "${OFFLINE-}" != 1 ] && ! { [ "${DROP_ROUTE_AFTER_NETD-}" = 1 ] && [ -f "$FORGE_FAKE_STATE/netd_restarted" ]; }; then
      printf '%s\n' 'default via 192.0.2.1 dev wlan0'
    fi
    ;;
  dumpsys)
    log "dumpsys:$*"
    count=$(cat "$FORGE_FAKE_STATE/validation_queries" 2>/dev/null || printf 0)
    count=$((count + 1))
    printf '%s\n' "$count" > "$FORGE_FAKE_STATE/validation_queries"
    if [ "${NO_VALIDATION-}" != 1 ] && [ "$count" -gt "${VALIDATION_DELAY-0}" ] &&
       ! { [ "${RUNTIME_VALIDATION_LOSS-}" = 1 ] && [ -f "$FORGE_FAKE_STATE/namespace_live" ] && [ ! -f "$FORGE_FAKE_STATE/netd_restarted" ]; }; then
      printf '%s\n' '  NetworkAgentInfo{ ni{[type: WIFI[]]} lastValidated{true} }'
    else
      printf '%s\n' '  NetworkAgentInfo{ ni{[type: WIFI[]]} lastValidated{false} }'
      printf '%s\n' 'old log: NetworkAgentInfo{ ni{[type: WIFI[]]} lastValidated{true} }'
      printf '%s\n' '  NetworkAgentInfo{ ni{[type: MOBILE[]]} lastValidated{true} }'
    fi
    ;;
  sleep) log "sleep:$1"; /bin/sleep 0.001 ;;
  tinymix|input) : ;;
  app_process) log surface-panel-started; exec /bin/sleep 5 ;;
  pidof) exit 1 ;;
  ps) exec /bin/ps "$@" ;;
  forge-namespace-run)
    /bin/sleep 5 & child=$!
    log "child:$child"
    printf '%s\n' "$child" > "$FORGE_FAKE_NAMESPACE_PID"
    mkdir -p "$FORGE_FAKE_PROC/$child/root/tmp/forge-surface" "$FORGE_FAKE_PROC/$child/root/tmp/.X11-unix"
    : > "$FORGE_FAKE_PROC/$child/root/tmp/forge-surface/Xvfb_screen0"
    : > "$FORGE_FAKE_PROC/$child/root/tmp/.X11-unix/X7"
    log namespace-ready
    : > "$FORGE_FAKE_STATE/namespace_live"
    trap 'kill "$child" 2>/dev/null; exit 143' TERM
    /bin/sleep "${FORGE_NAMESPACE_LIFETIME:-0.2}"
    log namespace-finished
    kill "$child" 2>/dev/null || :
    exit "${FORGE_NAMESPACE_RESULT:-124}"
    ;;
  *) echo "unexpected fake command: $name" >&2; exit 127 ;;
esac
'''


def run_session(
    tmp_path: Path, initial_states: dict[str, str] | None = None, mode: str = "1", **settings: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    install = tmp_path / "install"
    script = tmp_path / "forge-session.sh"
    # The lifecycle test uses host fakes and cannot write the device framebuffer.
    script.write_text(
        SCRIPT.read_text()
        .replace("/init.environ.rc", str(tmp_path / "init.environ.rc"))
        .replace("echo 0 > /sys/class/graphics/fb0/blank", ":")
        .replace("/proc/$namespace/root", "$FORGE_FAKE_PROC/$namespace/root")
        .replace('  namespace=$(ps -A -o PID,PPID 2>/dev/null | awk -v p="$service" \'$2==p {print $1; exit}\')', '  namespace=$(cat "$FORGE_FAKE_NAMESPACE_PID" 2>/dev/null || :)')
        .replace('  [ -n "$namespace" ] && [ -e "$FORGE_FAKE_PROC/$namespace/root/tmp/forge-surface/Xvfb_screen0" ] && break\n  sleep 0.1', '  [ -n "$namespace" ] && [ -e "$FORGE_FAKE_PROC/$namespace/root/tmp/forge-surface/Xvfb_screen0" ] && break\n  sleep 0.2')
    )
    script.chmod(0o755)
    (tmp_path / "init.environ.rc").write_text("export BOOTCLASSPATH /system/framework/framework.jar\nexport DEX2OATBOOTCLASSPATH /system/framework/framework.jar\n")
    root = install / "linux-root"
    bindir = tmp_path / "bin"
    state = tmp_path / "state"
    fake_proc = tmp_path / "proc"
    bindir.mkdir(parents=True)
    state.mkdir()
    initial_states = initial_states or {}
    for service, value in {"zygote": "running", "surfaceflinger": "running", "audioserver": "running", "netd": "running"}.items():
        value = initial_states.get(service, value)
        (state / service).write_text(value + "\n")
    for path in [
        install / "forge-surface.jar", install / "libforge-panel.so",
        root / "usr/local/bin/forge-browser-session", root / "usr/local/bin/forge-music-bridge",
        root / "usr/bin/Xvfb", root / "usr/lib/chromium/chromium", root / "opt/forge/forge-alsa-compat.so",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        path.chmod(0o755)
    panel = install / "forge-panel"
    panel.write_text("#!/bin/sh\nexec /bin/sleep 5\n")
    panel.chmod(0o755)
    namespace = install / "forge-namespace-run"
    namespace.write_text("#!/bin/sh\nexec forge-namespace-run \"$@\"\n")
    namespace.chmod(0o755)
    (install / "forge-cdp-guard.sh").write_text("forge_cdp_start() { :; }\nforge_cdp_stop() { :; }\n")
    fake = bindir / "fake-command"
    fake.write_text(DISPATCHER)
    fake.chmod(0o755)
    for command in "getprop stop start ip dumpsys sleep tinymix input pidof ps forge-namespace-run app_process".split():
        (bindir / command).symlink_to(fake.name)
    log = tmp_path / "commands.log"
    environment = os.environ | {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "FORGE_FAKE_LOG": str(log),
        "FORGE_FAKE_STATE": str(state),
        "FORGE_FAKE_PROC": str(fake_proc),
        "FORGE_FAKE_NAMESPACE_PID": str(tmp_path / "namespace.pid"),
        **settings,
    }
    result = subprocess.run(["/bin/sh", str(script), str(install), mode], text=True, capture_output=True, env=environment, timeout=10)
    return result, log.read_text().splitlines() if log.exists() else []


def test_stale_netd_ownership_is_cleared_before_zygote_returns(tmp_path: Path) -> None:
    result, log = run_session(tmp_path)

    assert result.returncode == 124
    assert "namespace-ready" in log
    netd_stop = log.index("stop:netd")
    netd_start = log.index("start:netd")
    zygote_start = log.index("start:zygote")
    assert netd_stop < netd_start < zygote_start
    assert any(entry.startswith("ip:-4 route show table wlan0") for entry in log)


def test_appliance_survives_validation_loss_until_browser_finishes(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, mode="appliance", RUNTIME_VALIDATION_LOSS="1",
                              FORGE_NAMESPACE_LIFETIME="1.5")
    assert result.returncode == 124
    assert "namespace-finished" in log
    assert "surface-panel-started" in log
    assert not any(entry.startswith(("stop:", "start:")) for entry in log)
    assert "Wi-Fi unavailable; returning to Android" not in result.stderr


def test_initially_stopped_services_are_not_started_or_reset(tmp_path: Path) -> None:
    result, log = run_session(
        tmp_path,
        initial_states={"zygote": "stopped", "surfaceflinger": "stopped", "audioserver": "stopped", "netd": "stopped"},
    )

    assert result.returncode == 124
    assert "stop:netd" not in log
    assert not any(entry in {"start:netd", "start:zygote", "start:surfaceflinger", "start:audioserver"} for entry in log)


def test_running_netd_is_preserved_when_zygote_was_already_stopped(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, initial_states={"zygote": "stopped", "netd": "running"})

    assert result.returncode == 124
    assert "stop:netd" not in log
    assert "start:netd" not in log


def test_offline_entry_guard_refuses_before_stopping_android(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, OFFLINE="1")

    assert result.returncode == 69
    assert "No wlan0 IPv4 default route" in result.stderr
    assert not any(entry.startswith("stop:") for entry in log)


def test_namespace_failure_still_runs_netd_cleanup(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, FORGE_NAMESPACE_RESULT="1")

    assert result.returncode == 1
    assert "namespace-ready" in log
    assert log.index("stop:netd") < log.index("start:netd") < log.index("start:zygote")


def test_failed_netd_restore_propagates_after_bounded_wait(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, FAIL_START_NETD="1")

    assert result.returncode == 70
    assert "could not start netd" in result.stderr
    assert "Forge cleanup completed with restoration failures" in result.stderr
    assert log.index("stop:netd") < log.index("start:netd") < log.index("start:zygote")
    assert log.count("sleep:0.1") == 50


def test_failed_netd_stop_wait_still_attempts_start_and_zygote_restore(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, FAIL_NETD_STOP_WAIT="1")

    assert result.returncode == 70
    assert "netd did not become stopped within 5 seconds" in result.stderr
    assert log.index("stop:netd") < log.index("start:netd") < log.index("start:zygote")
    assert "start:surfaceflinger" in log and "start:audioserver" in log
    assert log.count("sleep:0.1") == 100


def test_route_restore_poll_is_bounded_and_fails_loudly(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, DROP_ROUTE_AFTER_NETD="1")

    assert result.returncode == 70
    assert "wlan0 route and internet validation did not return within 60 recovery polls" in result.stderr
    assert log.count("sleep:1") >= 60
    assert not any(entry.startswith("dumpsys:") for entry in log)


def test_old_route_does_not_finish_recovery_before_new_wifi_validation(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, VALIDATION_DELAY="35")

    assert result.returncode == 124
    assert log.count("dumpsys:-t 1 connectivity") == 36


def test_route_alone_and_historical_or_mobile_validation_cannot_pass(tmp_path: Path) -> None:
    result, log = run_session(tmp_path, NO_VALIDATION="1")

    assert result.returncode == 70
    assert log.count("dumpsys:-t 1 connectivity") == 60
    assert "internet validation did not return" in result.stderr
