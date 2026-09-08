"""Exercise the real browser shell's argument passing and bridge restart."""
import os
from pathlib import Path
import subprocess


def test_bridge_restarts_with_appliance_arguments_without_restarting_browser(tmp_path):
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / 'state'
    fake = tmp_path / 'fake'
    fake.mkdir()
    scripts = {
        'xvfb': '#!/bin/sh\nexec sleep 8\n',
        'chromium': '#!/bin/sh\necho browser >> "$FORGE_TEST_EVENTS"\nexec sleep 3\n',
        'bridge': '''#!/bin/sh
for last; do :; done
printf 'bridge:%s\n' "$last" >> "$FORGE_TEST_EVENTS"
[ "$last" = --appliance ] || exit 64
if [ ! -e "$FORGE_TEST_ONCE" ]; then : > "$FORGE_TEST_ONCE"; exit 9; fi
exec sleep 8
''',
    }
    for name, text in scripts.items():
        path = fake / name
        path.write_text(text)
        path.chmod(0o755)
    text = (root / 'appliance/device/forge-browser-session.sh').read_text()
    for old, new in {
        '/var/lib/forge': str(state),
        '/tmp/forge-surface': str(tmp_path / 'surface'),
        '/etc/forge/home.url': str(tmp_path / 'absent-home.url'),
        '/usr/bin/Xvfb': str(fake / 'xvfb'),
        '/usr/lib/chromium/chromium': str(fake / 'chromium'),
        '/usr/local/bin/forge-music-bridge': str(fake / 'bridge'),
        'LD_PRELOAD=/opt/forge/forge-alsa-compat.so': 'LD_PRELOAD=',
    }.items():
        text = text.replace(old, new)
    script = tmp_path / 'session.sh'
    script.write_text(text)
    events = tmp_path / 'events'
    env = dict(os.environ, FORGE_TEST_EVENTS=str(events), FORGE_TEST_ONCE=str(tmp_path / 'once'))
    result = subprocess.run(['sh', str(script), 'appliance'], env=env, capture_output=True, text=True, timeout=9)
    assert result.returncode == 0, result.stderr
    lines = events.read_text().splitlines()
    assert lines.count('browser') == 1
    assert lines.count('bridge:--appliance') == 2
    assert 'Restarting music controls' in result.stdout
