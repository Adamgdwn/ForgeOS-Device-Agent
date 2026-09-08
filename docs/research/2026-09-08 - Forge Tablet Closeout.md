# Forge tablet closeout

Last Updated: 2026-09-08T17:45:02-06:00
Status: installed personal appliance; selected playback and Cast verified, with a material responsiveness limitation. Engineering work is stopped for the night after repository publication.

## Outcome and scope

The Samsung **SM-T377W / gteslte** has been repurposed as an always-powered, Wi-Fi music and home-control tablet. YouTube Music Premium is the primary service; Home Assistant is the secondary dashboard. The owner confirmed clear local audio, working music selection and dashboard navigation, and clear Cast audio in the kitchen. Later testing was explicitly authorized on Main Speakers.

Forge now boots independently of Android. Its green retro interface is original native C code. A custom C init starts networking, display, touch, audio and a private Linux browser service. The hardware kernel remains the device-specific **Linux 3.10.108** kernel with its matching device tree. This is a custom Linux appliance using the existing hardware kernel; a new kernel was not written. YouTube Music runs in Chromium, not in the official Android application.

This closeout supersedes the historical Android launcher, JNI surface and clean-Android trial plans for describing the installed device. Those components remain in source for provenance and regression coverage. They are not the normal boot path.

## Installed architecture

| Layer | Installed responsibility |
| --- | --- |
| BOOT / PID 1 | Static Forge init, service startup and bounded recovery |
| Hardware | Existing Samsung kernel/device tree; native framebuffer and evdev touch |
| Network | Linux Wi-Fi association, DHCP and renewal supervision |
| Interface | Native Music, Browse and Home screens; keyboard and browser-surface input |
| Application runtime | Private Debian ARM32 rootfs, Chromium 150 and Xvfb |
| Local audio | Linux ALSA with an old-kernel compatibility shim |
| Music controls | Native bridge to the signed-in browser's player and Cast session |
| Home controls | Saved Home Assistant dashboard in the second browser tab |
| Recovery | Preserved physical recovery and workstation image backups |

Android SYSTEM, USERDATA and CACHE were formatted during the completed migration. The resulting partitions hold `/os`, `/data` and Forge cache. Runtime is under `/os/root`; private configuration and browser state are under `/data/forge/state`. No Android framework, SurfaceFlinger, audio service, Java host or Android network service starts.

The browser runs as UID 65000 with private namespaces and no capabilities. Its control service is local. This is containment for a personal appliance, not a claim of a fully hardened or vendor-supported operating system. Account and Wi-Fi state remain private on the tablet.

## Final song-selection repairs

Two separate problems were established and repaired:

1. **A stalled invisible player overlay swallowed song taps.** A site animation remained pending with no start time. The bridge now finishes only the narrowly matched, unchanged, short player-page transition after observing it stalled for two seconds. Normal animations and other pages are untouched.
2. **Synchronous queue rendering blocked the browser for tens of seconds.** A 100-entry queue caused heavy Polymer/ShadyDOM element creation. The bridge now renders the selected portion first, then completes the remaining queue in small batches. Canonical queue data and original ordering are retained; the complete queue eventually renders.

The queue helper uses exact-origin and component guards, preserves prefix indices, cancels obsolete work, checks function ownership and handles throwing accessors. If its assumptions fail, it restores the original renderer and attempts full rendering. Independent QA found two initial ownership/accessor defects; both were corrected with executable regression cases before installation.

These maintenance operations run outside control-action cycles. STATE remains read-only. The repairs do not extract media URLs, change credentials, modify the Cast protocol, or issue duplicate playback commands. The same browser and display processes survived installation.

## Measured evidence and practical limits

Song-change timings use a native tablet tap and a separate read-only receiver query. A pass required the exact requested title plus advancing receiver playback position. Browser metadata alone was not accepted as proof of speaker playback.

| Observation | Time to first matching playback | Evidence stage |
| --- | ---: | --- |
| Earlier unoptimized song selection | 43.277 s | Baseline live receiver |
| Progressive queue candidate selection | 14.139 s | Candidate live receiver |
| Two rapid taps, final requested song wins | 17.465 s | Candidate live receiver |
| Final installed native Next | 7.794 s | Installed live receiver |
| Final installed Browse song selection | 18.445 s | Installed live receiver |

These are individual trials, not a statistical latency guarantee. Selected tracks reached Main Speakers correctly. **The remaining roughly 14–19-second song-change delay is still a usability problem.** The final installed build must not be described as instant or as having completely solved responsiveness. A final optional owner check was not answered before closeout; the owner requested documentation, commit and push instead. No further user action is needed tonight.

The baseline trace contained a 33.451-second synchronous task dominated by queue DOM creation and garbage collection. Network headers arrived promptly, but the renderer processed the response much later. A temporary four-row experiment reduced its longest measured task to 1.951 seconds; that number belongs to the experiment, not to a fresh trace of the installed progressive helper.

Earlier standalone hardware verification established:

- Owner-confirmed clear local YouTube Music audio and working Select Music / Home → Open Dashboard.
- A real Home Assistant light change with state confirmation and restoration.
- Wi-Fi association recovery in 4.1 seconds after a five-second interruption, followed by DHCP renewal and working applications.
- Display-process recovery in 1.71 seconds and bridge recovery in 1.08 seconds while preserving the browser and audio.
- Kitchen Cast connection through the ordinary touchscreen chooser, owner-confirmed audio, native transport/volume controls and approximately 62 seconds of advancing remote playback with local audio paused.

Those checks predate the final queue helper. Home automation, cold boot and prolonged endurance were not repeated for this final bridge-only installation. Cold YouTube Music initialization has taken two to three minutes. Long-duration unattended streaming, repeated cold boots and overnight network recovery remain future acceptance work. Google account concurrent-stream limits still apply.

## Verification and release judgment

The closeout governance run passed **246 tests, 1 skipped and 2 subtests in 61.53 seconds**, with Python compilation and the repository secret scan passing. The [final preflight log](../../evidence/public/2026-09-08-preflight.txt) is included. Project control remains medium risk, governance level 2, A1, sensitive-data handling, no money movement and no open exceptions.

The implementation packet also passed strict ARM compilation with warnings treated as errors, 21 JavaScript helper tests and exact CDP buffer-size checks. Independent QA accepted the corrected helper conditionally; root then completed device installation, receiver-based playback validation and full preflight. The installed build and rollback hashes were re-read during closeout.

Release judgment: preserve the installed improvements as a verified personal-appliance increment. Correct selected playback is established for the tested flows. General responsiveness and endurance remain open. No additional firmware or runtime experiment is part of tonight's closeout.

## Installed identifiers and rollback

| Artifact | SHA-256 |
| --- | --- |
| Permanent BOOT partition | `0c66bc8b8e39ac1bf9f91ed34b0ab6499665c93068f84dae5019c180f9d1fac1` |
| Current music bridge | `06bebf15da91c048e204d26d75f4a66a8699ebddc44ca0762509b39ba0413b78` |
| Bridge before queue batching, with tap repair | `6a51c5eec6555a8ec0dcb67b32aede442f978305929af4c342649c6ebd5ef90e` |
| Bridge before both selection repairs | `c53d80b989db402b3c3596431744569a8f2516916508ae40a2f6a89b847fd1b6` |

Current device binary: `/os/root/usr/local/bin/forge-music-bridge`.
Matching host artifact: `output/native-arm/forge-music-bridge`.
The two on-device backups append `.before-queue-batching` and `.before-selection-repair` to the current binary path. The BOOT hash is from prior full partition readback; BOOT was not rewritten or re-read during this closeout.

For a bridge regression, first record the current status and verify the intended backup hash. Copy that backup to a new file alongside the current binary, set mode 755, then atomically rename it over the installed path. Preserve the current binary separately. Restart only the verified bridge under its actual service UID or perform a planned service restart. The restricted administrative shell cannot signal UID 65000 processes directly; the previous update used a narrowly checked UID-dropping helper. Do not blindly kill remembered process IDs. The supervisor permits only three bridge failures per browser session; repeated trial restarts can terminate the wider session.

The installed JavaScript is page-local. Replacing the binary alone does not necessarily undo a helper already loaded in the current page. A complete rollback must restore that helper or start a fresh music page/session, then verify the normal Cast chooser, exact selected track, local-audio state and Home Assistant tab. Preserve sign-ins and browser tab order. A reload can interrupt Cast and take minutes, so rollback is a maintenance operation, not an action taken tonight.

Original verified BOOT and RECOVERY images are in `output/standalone/boot-verified.img` and `output/standalone/recovery-verified.img`; both files were confirmed present during closeout. The local appliance manifest is `output/standalone/appliance-manifest.json`. They are not published to Git. **Restoring the old BOOT alone cannot recreate Android after its filesystems were erased.** Preserve recovery, EFS, radio and bootloader partitions. Never replay `migrate-in-recovery.sh` on the finished appliance.

## Build and continuation

The native Makefile supports host and ARM builds. For the final bridge, the proven compiler is NDK 27.1's `armv7a-linux-androideabi21-clang`, with:

```sh
-O2 -std=c11 -Wall -Wextra -Werror -D_POSIX_C_SOURCE=200809L -static -ffunction-sections -fdata-sections -pthread -Wl,--gc-sections -s
```

Compile `appliance/native/music_bridge.c` with its adjacent headers. Section garbage collection is required for the demonstrated static ARM build; omitting it previously produced a Bionic TLS startup abort. Generated binaries, the Debian rootfs, vendor kernel/device tree and firmware backups are local build inputs. This source commit is not a self-contained downloadable tablet image.

For public source privacy, init now defaults to the generic USB identity
`forge-gteslte`, with a compile-time `FORGE_USB_SERIAL` override. The owner
serial previously embedded in the source was removed before staging the final
commit. This source-only publication change is not installed: the running BOOT
and bridge hashes above are unchanged. A future rebuild will use the generic
identity unless explicitly configured. Strict ARM compilation and the final
preflight cover this small source change; hardware USB enumeration of that
rebuild has not been tested.

See the [standalone operating guide](../../appliance/standalone/README.md), [native component guide](../../appliance/native/README.md) and [public evidence summary](../../evidence/public/2026-09-08-closeout.json). Full raw measurements, historical plans, private operational checkpoints and local backups remain on the workstation; they are deliberately excluded from the public repository. Public evidence contains aggregate timing and verification outcomes, without receiver addresses, device serials, credentials or media URLs.

The next engineering packet should start from the local root checkpoint and installed hashes, preserve the working Cast path, and measure the remaining delay. A possible next hypothesis is full-queue teardown cost; it has not been established or implemented. Any further optimization must preserve the identity and order of visible song choices and use the independent receiver oracle. Do not repeat disproven approaches without new evidence:

- Forcing native Shadow DOM broke the site's compiled CSS.
- CSS containment, browser zoom and reducing bridge polling did not solve the delay.
- Direct player SDK load calls changed a browser facade without controlling the actual Cast receiver.
- Temporary CDP `Cast.setSinkToUse` corrupted the normal chooser callback; use native selection and read-only monitoring instead.

## State left for the night

The final read-only check reports connected music controls, no fault, READY, empty notice and `playing=0`; local PCM is closed. The tablet was left powered with its existing signed-in browser session. This records the observed state; it does not claim music continued playing at closeout or that the device was powered off.

ADB development forwards are absent, `/run/forge-usb` is empty and hotplug is `/bin/mdev`. Earlier profiling, browser diagnostics, role runs and monitors completed and were reaped; temporary screenshots and the host diagnostic browser attachment were removed. No new playback test, reboot, service restart or shutdown was issued for this documentation packet. The final closeout QA and preflight jobs completed successfully. Independent QA recommended release of the exact staged public payload after checking privacy, source scope and evidence claims. No background engineering job remains or is authorized to continue overnight.

The commit includes the standalone appliance implementation, relevant regression tests, the ADB partition-probe fix, corrected operating guides and this closeout. Unrelated root README path-migration edits and the Portfolio Status working document are preserved locally. The remote's existing MIT-license addition was fast-forwarded before this commit. The Git commit containing this document and its parent graph provide publication identity; final local/remote equality is verified after push and reported to the owner.
