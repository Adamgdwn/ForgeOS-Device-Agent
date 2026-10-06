# Next Steps

## Live Device Integration

1. Replace stubbed adapter calls in [app/integrations/adb.py](app/integrations/adb.py), [app/integrations/fastboot.py](app/integrations/fastboot.py), and [app/integrations/fastbootd.py](app/integrations/fastbootd.py) with real subprocess execution, structured parsing, timeout control, and transport retry logic.
2. Add real udev event integration in [app/watchers/udev_listener.py](app/watchers/udev_listener.py), ideally through `pyudev`, so attach/detach events do not rely only on polling.
3. Implement restore feasibility discovery in [app/tools/backup_restore.py](app/tools/backup_restore.py) and [app/tools/restore_controller.py](app/tools/restore_controller.py) for partition snapshots, factory image lookup, and rollback playbooks.
4. Connect source manifests and build strategies in [master/manifests/sources.json](master/manifests/sources.json) and [master/strategies/default_strategies.json](master/strategies/default_strategies.json) to real Android distribution metadata.
5. Add signing pipeline integration in [app/tools/avb_signer.py](app/tools/avb_signer.py) with AVB key management, release-vs-lab signing modes, and rotation controls.
6. Expand validation in [app/tools/boot_validator.py](app/tools/boot_validator.py), [app/tools/hardware_bringup.py](app/tools/ota_tester.py](app/tools/ota_tester.py), and [master/testplans/default_validation_plan.json](master/testplans/default_validation_plan.json) to cover Wi-Fi, Bluetooth, radio, charging, suspend, and OTA rollback paths.

## Productization

1. Add a richer desktop UI in `app/gui/` for approval prompts, device session status, and audit log review.
2. Package the launcher and Python environment for Pop!_OS with a stable install target under `~/.local/share/applications`.
3. Add a background service mode for continuous monitoring outside the foreground app lifecycle.
4. Expand the controlled learning layer so promotion candidates can attach validation evidence, regression notes, and human review outcomes before master updates are accepted.
