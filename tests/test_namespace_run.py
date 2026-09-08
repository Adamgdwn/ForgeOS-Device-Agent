"""Host-only safety contracts for the bounded namespace supervisor.

These tests intentionally stop before ``unshare``: the live namespace/mount
path is reserved for the separately controlled ARM device experiment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "appliance" / "native" / "namespace_run.c"


@pytest.fixture(scope="module")
def namespace_runner(tmp_path_factory: pytest.TempPathFactory) -> Path:
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for namespace boundary test")
    output = tmp_path_factory.mktemp("namespace-run") / "forge-namespace-run"
    result = subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-D_POSIX_C_SOURCE=200809L",
            str(SOURCE),
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return output


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--root", "/tmp", "--seconds", "0", "--", "/bin/true"],
        ["--root", "relative", "--seconds", "1", "--", "/bin/true"],
        ["--root", "/tmp", "--seconds", "1801", "--", "/bin/true"],
        ["--root", "/tmp", "--seconds", "1"],
    ],
    ids=["empty", "zero-deadline", "relative-root", "deadline-ceiling", "missing-command"],
)
def test_namespace_runner_rejects_invalid_cli_before_privileged_work(
    namespace_runner: Path, arguments: list[str]
) -> None:
    result = subprocess.run([str(namespace_runner), *arguments], capture_output=True, text=True, timeout=5)
    assert result.returncode == 64


def test_namespace_runner_prints_usage_for_an_unknown_option(namespace_runner: Path) -> None:
    result = subprocess.run([str(namespace_runner), "--invalid"], capture_output=True, text=True, timeout=5)
    assert result.returncode == 64
    assert "Usage:" in result.stderr


def test_namespace_runner_refuses_nonroot_before_namespace_setup(namespace_runner: Path, tmp_path: Path) -> None:
    """A non-root invocation must stop at the explicit privilege boundary."""
    command = [str(namespace_runner), "--root", str(tmp_path), "--seconds", "1", "--", "/bin/true"]
    if os.geteuid() == 0:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            preexec_fn=lambda: os.setuid(65534),
        )
    else:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    assert result.returncode == 77
    assert "root is required" in result.stderr


def test_namespace_runner_rejects_writable_rootfs_before_unshare(namespace_runner: Path, tmp_path: Path) -> None:
    """The rootfs gate must fail without entering a host namespace or mounting."""
    if os.geteuid() != 0:
        pytest.skip("rootfs ownership gate is reachable only from a root test process")
    tmp_path.chmod(0o777)
    result = subprocess.run(
        [str(namespace_runner), "--root", str(tmp_path), "--seconds", "1", "--", "/bin/true"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 77
    assert "private root-owned directory" in result.stderr


def test_close_fds_closes_an_inherited_descriptor_but_keeps_stdio(tmp_path: Path) -> None:
    """The unprivileged service must not inherit a launcher's host handles."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for descriptor-boundary test")
    harness = tmp_path / "close-fds-boundary.c"
    harness.write_text(
        f'''\
#define main namespace_runner_program_main
#include "{SOURCE}"
#undef main

int main(void) {{
    int sentinel = open("/dev/null", O_RDONLY);
    if (sentinel < 3) return 10;
    if (close_fds() != 0) return 11;
    if (fcntl(sentinel, F_GETFD) != -1 || errno != EBADF) return 12;
    for (int fd = 0; fd < 3; ++fd)
        if (fcntl(fd, F_GETFD) == -1 && errno == EBADF) return 13;
    return 0;
}}
'''
    )
    output = tmp_path / "close-fds-boundary"
    result = subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-D_POSIX_C_SOURCE=200809L",
            str(harness),
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(output)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0


def test_directory_helper_restores_requested_modes_despite_a_restrictive_umask(tmp_path: Path) -> None:
    """Exercise the real helper without entering a namespace or mounting anything."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for directory-mode boundary test")

    fresh = tmp_path / "fresh"
    existing = tmp_path / "existing"
    sticky = tmp_path / "sticky"
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "directory-link"
    link.symlink_to(target, target_is_directory=True)
    regular = tmp_path / "not-a-directory"
    regular.write_text("not a directory")

    harness = tmp_path / "directory-mode-boundary.c"
    harness.write_text(
        f'''\
#define main namespace_runner_program_main
#include "{SOURCE}"
#undef main

static int expect_mode(const char *path, mode_t expected) {{
    struct stat status;
    return lstat(path, &status) || (status.st_mode & 07777) != expected;
}}

int main(int argc, char **argv) {{
    if (argc != 6) return 2;
    umask(0077);
    if (directory(argv[1], 0755) || expect_mode(argv[1], 0755)) return 10;
    if (mkdir(argv[2], 0700) || directory(argv[2], 0755) || expect_mode(argv[2], 0755)) return 11;
    if (directory(argv[3], 01777) || expect_mode(argv[3], 01777)) return 12;
    if (directory(argv[4], 0755) == 0 || errno != EINVAL) return 13;
    if (directory(argv[5], 0755) == 0 || errno != EINVAL) return 14;
    return 0;
}}
'''
    )
    output = tmp_path / "directory-mode-boundary"
    result = subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-D_POSIX_C_SOURCE=200809L",
            str(harness),
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [str(output), str(fresh), str(existing), str(sticky), str(link), str(regular)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr


def test_namespace_source_confines_kill_all_after_pid1_and_private_mount_gates() -> None:
    """Audit ordering without creating namespaces, mounts, or processes."""
    source = SOURCE.read_text()
    namespace_body = source[source.index("static int run_namespace") : source.index("int main(")]
    assert namespace_body.index("if(getpid()!=1)") < namespace_body.index("kill(-1,SIGTERM)")
    assert namespace_body.index("if(getpid()!=1)") < namespace_body.index("kill(-1,SIGKILL)")
    assert "setgroups(1,groups)||setgid(65000)||setuid(65000)||prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)" in namespace_body

    root_gate = source.index("if(!realpath(root,resolved)")
    unshare_gate = source.index("if(unshare(CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWIPC|CLONE_NEWUTS)")
    private_mount = source.index("mount(NULL,\"/\",NULL,MS_REC|MS_PRIVATE,NULL)")
    namespace_fork = source.index("pid_t init=fork()")
    assert root_gate < unshare_gate < private_mount < namespace_fork
    assert "s.st_uid!=0" in source[root_gate:unshare_gate]
    assert "(s.st_mode&0022)" in source[root_gate:unshare_gate]
    assert source.index("kill(init,SIGTERM)") < source.index("kill(init,SIGKILL)")
