from __future__ import annotations

from app.core.models import SessionStateName


ALLOWED_TRANSITIONS: dict[SessionStateName, set[SessionStateName]] = {
    SessionStateName.IDLE: {SessionStateName.DISCOVER},
    SessionStateName.DISCOVER: {SessionStateName.ASSESS, SessionStateName.BLOCKED},
    SessionStateName.ASSESS: {
        SessionStateName.BACKUP_PLAN,
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BACKUP_PLAN: {
        SessionStateName.UNLOCK_PREP,
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKED,
    },
    SessionStateName.UNLOCK_PREP: {SessionStateName.UNLOCK, SessionStateName.BLOCKED},
    SessionStateName.UNLOCK: {SessionStateName.BASELINE_CAPTURE, SessionStateName.BLOCKED},
    SessionStateName.BASELINE_CAPTURE: {
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKED,
    },
    SessionStateName.PATH_SELECT: {
        SessionStateName.BUILD_GENERIC,
        SessionStateName.BUILD_DEVICE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BUILD_GENERIC: {SessionStateName.SIGN_IMAGES, SessionStateName.BLOCKED},
    SessionStateName.BUILD_DEVICE: {SessionStateName.SIGN_IMAGES, SessionStateName.BLOCKED},
    SessionStateName.SIGN_IMAGES: {SessionStateName.FLASH_PREP, SessionStateName.BLOCKED},
    SessionStateName.FLASH_PREP: {SessionStateName.FLASH, SessionStateName.BLOCKED},
    SessionStateName.FLASH: {
        SessionStateName.BOOTSTRAP_DEVICE,
        SessionStateName.RESTORE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BOOTSTRAP_DEVICE: {
        SessionStateName.BRINGUP,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BRINGUP: {SessionStateName.HARDEN, SessionStateName.BLOCKED},
    SessionStateName.HARDEN: {SessionStateName.VALIDATE, SessionStateName.BLOCKED},
    SessionStateName.VALIDATE: {
        SessionStateName.PROMOTE,
        SessionStateName.RESTORE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.PROMOTE: set(),
    SessionStateName.RESTORE: {SessionStateName.ASSESS, SessionStateName.BLOCKED},
    SessionStateName.BLOCKED: {SessionStateName.ASSESS},
}


def is_transition_allowed(current: SessionStateName, target: SessionStateName) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
