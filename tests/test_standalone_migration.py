"""Wipe prerequisite: on-device copy verifier detects material copy failures."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope='module')
def verifier(tmp_path_factory):
    out = tmp_path_factory.mktemp('tree-verifier') / 'verify'
    source = Path(__file__).resolve().parents[1] / 'appliance/standalone/verify_tree.c'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(out)], check=True, timeout=30)
    return out


@pytest.mark.parametrize('damage', ['none', 'content', 'extra', 'mode', 'symlink'])
def test_tree_copy_verification(verifier, tmp_path, damage):
    src, dst = tmp_path / 'source', tmp_path / 'target'
    src.mkdir()
    (src / 'private').write_bytes(b'example fixture\x00' * 5000)
    (src / 'link').symlink_to('private')
    shutil.copytree(src, dst, symlinks=True)
    if damage == 'content':
        (dst / 'private').write_bytes(b'x' * (src / 'private').stat().st_size)
    elif damage == 'extra':
        (dst / 'extra').touch()
    elif damage == 'mode':
        (dst / 'private').chmod(0o700)
    elif damage == 'symlink':
        (dst / 'link').unlink()
        (dst / 'link').symlink_to('missing')
    result = subprocess.run([str(verifier), str(src), str(dst)], capture_output=True, text=True, timeout=5)
    assert (result.returncode == 0) == (damage == 'none')
    assert 'private' not in result.stdout and 'example' not in result.stdout
