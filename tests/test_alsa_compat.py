from __future__ import annotations

import subprocess
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sync_ptr_compatibility_contract(tmp_path: Path) -> None:
    harness = tmp_path / "alsa_compat_harness.c"
    executable = tmp_path / "alsa_compat_harness"
    harness.write_text(
        r'''#include <assert.h>
        #include <errno.h>
        #include <stdint.h>
        #define FORGE_ALSA_COMPAT_TEST 1
        #include "appliance/linux_service/alsa_compat.c"

        static int mode;
        static unsigned long last_request;
        int forge_alsa_compat_test_ioctl(int fd, unsigned long request, void *arg) {
            uint32_t *words = arg;
            (void)fd;
            last_request = request;
            if (mode == 1) return 7;
            if (mode == 4) { errno = ENOTTY; return -1; }
            if (request == FORGE_SYNC_PTR_TIME64) { errno = ENOTTY; return -1; }
            if (mode == 3) { errno = EIO; return -1; }
            assert(request == FORGE_SYNC_PTR_LEGACY);
            assert(words[4] == 0xfffffffeU && words[5] == 44U);
            assert(words[7] == 0x80000001U && words[8] == 55U);
            assert(words[17] == 0x12345678U && words[18] == 0xabcdef01U);
            words[4] = 0xfffffffdU; words[5] = 66U;
            words[7] = 2U; words[8] = 77U;
            words[17] = 0x13579bdfU; words[18] = 0x2468ace0U;
            return 0;
        }
        int main(void) {
            uint32_t sync[FORGE_TIME64_WORDS] = {0};
            sync[6] = 0xfffffffeU; sync[8] = 44U;
            sync[12] = 0x80000001U; sync[14] = 55U;
            sync[18] = 0x12345678U; sync[19] = 0xabcdef01U;
            assert(forge_alsa_compat_ioctl(3, FORGE_SYNC_PTR_TIME64, sync) == 0);
            assert(sync[6] == 0xfffffffdU && sync[7] == 0xffffffffU && sync[8] == 66U && sync[9] == 0);
            assert(sync[12] == 2U && sync[13] == 0 && sync[14] == 77U && sync[15] == 0);
            assert(sync[18] == 0x13579bdfU && sync[19] == 0x2468ace0U);
            mode = 1;
            assert(forge_alsa_compat_ioctl(3, FORGE_SYNC_PTR_TIME64, sync) == 7);
            assert(last_request == FORGE_SYNC_PTR_TIME64);
            mode = 4; errno = 0;
            assert(forge_alsa_compat_ioctl(3, 0x1234UL, sync) == -1 && errno == ENOTTY);
            assert(last_request == 0x1234UL);
            errno = 0; assert(forge_alsa_compat_ioctl(3, FORGE_SYNC_PTR_TIME64, 0) == -1 && errno == EFAULT);
            mode = 3; errno = 0;
            assert(forge_alsa_compat_ioctl(3, FORGE_SYNC_PTR_TIME64, sync) == -1 && errno == EIO);
            return 0;
        }'''
    )
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(harness), "-o", str(executable)],
        check=True,
    )
    subprocess.run([str(executable)], check=True)


def test_exported_time64_interposer_binds_to_next_loader_symbol(tmp_path: Path) -> None:
    """Exercise the public preload symbol, rather than the unit-test seam."""
    backend = tmp_path / "libfake_ioctl_backend.so"
    interposer = tmp_path / "forge-alsa-compat-host.so"
    client = tmp_path / "alsa_preload_client"
    backend_source = tmp_path / "fake_ioctl_backend.c"
    client_source = tmp_path / "alsa_preload_client.c"
    backend_source.write_text(
        r'''#include <errno.h>
        #include <stdint.h>
        #include <stdlib.h>
        static unsigned long requests[2]; static int calls;
        int __ioctl_time64(int fd, unsigned long request, void *arg) {
            uint32_t *words = arg; (void)fd; requests[calls++] = request;
            if (request == 0xc0884123UL) { errno = ENOTTY; return -1; }
            if (request != 0xc0844123UL) { errno = EINVAL; return -1; }
            if (words[4] != 0xfffffffeU || words[5] != 44U ||
                words[7] != 0x80000001U || words[8] != 55U ||
                words[17] != 0x12345678U || words[18] != 0xabcdef01U) abort();
            words[4] = 0xfffffffdU; words[5] = 66U;
            words[7] = 2U; words[8] = 77U;
            words[17] = 0x13579bdfU; words[18] = 0x2468ace0U;
            return 0;
        }
        int fake_call_count(void) { return calls; }
        unsigned long fake_request(int index) { return requests[index]; }'''
    )
    client_source.write_text(
        r'''#include <assert.h>
        #include <errno.h>
        #include <stdint.h>
        extern int __ioctl_time64(int, unsigned long, void *);
        extern int fake_call_count(void); extern unsigned long fake_request(int);
        int main(void) {
            uint32_t sync[34] = {0};
            sync[6] = 0xfffffffeU; sync[8] = 44U;
            sync[12] = 0x80000001U; sync[14] = 55U;
            sync[18] = 0x12345678U; sync[19] = 0xabcdef01U;
            errno = EDOM;
            assert(__ioctl_time64(3, 0xc0884123UL, sync) == 0);
            assert(errno == EDOM);
            assert(fake_call_count() == 2);
            assert(fake_request(0) == 0xc0884123UL && fake_request(1) == 0xc0844123UL);
            assert(sync[6] == 0xfffffffdU && sync[7] == 0xffffffffU && sync[8] == 66U && sync[9] == 0);
            assert(sync[12] == 2U && sync[13] == 0 && sync[14] == 77U && sync[15] == 0);
            assert(sync[18] == 0x13579bdfU && sync[19] == 0x2468ace0U);
            return 0;
        }'''
    )
    subprocess.run(
        ["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror", str(backend_source), "-o", str(backend)],
        check=True,
    )
    subprocess.run(
        ["cc", "-shared", "-fPIC", "-D__arm__", "-std=c11", "-Wall", "-Wextra", "-Werror",
         str(ROOT / "appliance/linux_service/alsa_compat.c"), "-ldl", "-o", str(interposer)],
        check=True,
    )
    subprocess.run(
        ["cc", "-Wall", "-Wextra", "-Werror", str(client_source), "-L", str(tmp_path), "-lfake_ioctl_backend",
         "-Wl,-rpath," + str(tmp_path), "-o", str(client)],
        check=True,
    )
    environment = os.environ | {"LD_PRELOAD": str(interposer)}
    subprocess.run([str(client)], check=True, env=environment)


def test_armhf_build_exports_time64_interposer() -> None:
    subprocess.run([str(ROOT / "appliance/linux_service/build-alsa-compat.sh")], check=True)
    artifact = ROOT / "output/native-arm/forge-alsa-compat.so"
    symbols = subprocess.run(["readelf", "--dyn-syms", "--wide", str(artifact)], check=True, text=True,
                             capture_output=True).stdout
    assert " __ioctl_time64" in symbols
