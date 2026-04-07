from __future__ import annotations

from app.core.models import SessionStateName


ALLOWED_TRANSITIONS: dict[SessionStateName, set[SessionStateName]] = {
    SessionStateName.IDLE: {
        SessionStateName.DEVICE_ATTACHED,
        SessionStateName.INTAKE,
        SessionStateName.DISCOVER,
    },
    SessionStateName.DEVICE_ATTACHED: {
        SessionStateName.INTAKE,
        SessionStateName.ACCESS_ENABLEMENT,
        SessionStateName.DISCOVER,
        SessionStateName.BLOCKED,
    },
    SessionStateName.INTAKE: {
        SessionStateName.ACCESS_ENABLEMENT,
        SessionStateName.DISCOVER,
        SessionStateName.BLOCKED,
    },
    SessionStateName.ACCESS_ENABLEMENT: {
        SessionStateName.DEEP_SCAN,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.DISCOVER: {
        SessionStateName.DEEP_SCAN,
        SessionStateName.ASSESS,
        SessionStateName.PROFILE_SYNTHESIS,
        SessionStateName.BLOCKED,
    },
    SessionStateName.DEEP_SCAN: {
        SessionStateName.PROFILE_SYNTHESIS,
        SessionStateName.ASSESS,
        SessionStateName.BLOCKED,
    },
    SessionStateName.PROFILE_SYNTHESIS: {
        SessionStateName.ASSESS,
        SessionStateName.MATCH_MASTER,
        SessionStateName.BLOCKED,
    },
    SessionStateName.MATCH_MASTER: {
        SessionStateName.ASSESS,
        SessionStateName.RECOMMEND,
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKED,
    },
    SessionStateName.ASSESS: {
        SessionStateName.RECOMMEND,
        SessionStateName.BACKUP_PLAN,
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKER_CLASSIFY,
        SessionStateName.BLOCKED,
    },
    SessionStateName.RECOMMEND: {
        SessionStateName.BACKUP_PLAN,
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BACKUP_PLAN: {
        SessionStateName.BACKUP_READY,
        SessionStateName.UNLOCK_PREP,
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BACKUP_READY: {
        SessionStateName.PREVIEW_BUILD,
        SessionStateName.FLASH_PREP,
        SessionStateName.BUILD_GENERIC,
        SessionStateName.BUILD_DEVICE,
        SessionStateName.ITERATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.UNLOCK_PREP: {SessionStateName.UNLOCK, SessionStateName.BLOCKED},
    SessionStateName.UNLOCK: {SessionStateName.BASELINE_CAPTURE, SessionStateName.BLOCKED},
    SessionStateName.BASELINE_CAPTURE: {
        SessionStateName.PATH_SELECT,
        SessionStateName.BLOCKED,
    },
    SessionStateName.PATH_SELECT: {
        SessionStateName.BLOCKER_CLASSIFY,
        SessionStateName.BUILD_GENERIC,
        SessionStateName.BUILD_DEVICE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BLOCKER_CLASSIFY: {
        SessionStateName.REMEDIATION_DECIDE,
        SessionStateName.CODEGEN_TASK,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BUILD_GENERIC,
        SessionStateName.BUILD_DEVICE,
        SessionStateName.ITERATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.REMEDIATION_DECIDE: {
        SessionStateName.TASK_CREATE,
        SessionStateName.QUESTION_GATE,
        SessionStateName.CONNECTIVITY_VALIDATE,
        SessionStateName.SECURITY_VALIDATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.TASK_CREATE: {
        SessionStateName.CODEGEN_WRITE,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.CODEGEN_TASK: {
        SessionStateName.CODEGEN_WRITE,
        SessionStateName.PATCH_APPLY,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.CODEGEN_WRITE: {
        SessionStateName.PATCH_APPLY,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.PATCH_APPLY: {
        SessionStateName.EXECUTE_ARTIFACT,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.EXECUTE_ARTIFACT: {
        SessionStateName.INSPECT_RESULT,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.INSPECT_RESULT: {
        SessionStateName.BLOCKER_CLASSIFY,
        SessionStateName.CONNECTIVITY_VALIDATE,
        SessionStateName.SECURITY_VALIDATE,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.EXECUTE_STEP: {
        SessionStateName.CONNECTIVITY_VALIDATE,
        SessionStateName.SECURITY_VALIDATE,
        SessionStateName.ITERATE,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.CONNECTIVITY_VALIDATE: {
        SessionStateName.ITERATE,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.SECURITY_VALIDATE: {
        SessionStateName.ITERATE,
        SessionStateName.QUESTION_GATE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.ITERATE: {
        SessionStateName.BLOCKER_CLASSIFY,
        SessionStateName.PATH_SELECT,
        SessionStateName.DEEP_SCAN,
        SessionStateName.BUILD_GENERIC,
        SessionStateName.BUILD_DEVICE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.QUESTION_GATE: {
        SessionStateName.EXECUTE_STEP,
        SessionStateName.FLASH_PREP,
        SessionStateName.BLOCKER_CLASSIFY,
        SessionStateName.BACKUP_READY,
        SessionStateName.BLOCKED,
    },
    SessionStateName.BUILD_GENERIC: {SessionStateName.SIGN_IMAGES, SessionStateName.BLOCKED},
    SessionStateName.BUILD_DEVICE: {SessionStateName.SIGN_IMAGES, SessionStateName.BLOCKED},
    SessionStateName.PREVIEW_BUILD: {
        SessionStateName.PREVIEW_REVIEW,
        SessionStateName.INTERACTIVE_VERIFY,
        SessionStateName.BLOCKED,
    },
    SessionStateName.PREVIEW_REVIEW: {
        SessionStateName.INTERACTIVE_VERIFY,
        SessionStateName.BLOCKED,
    },
    SessionStateName.INTERACTIVE_VERIFY: {
        SessionStateName.INSTALL_APPROVAL,
        SessionStateName.BLOCKED,
    },
    SessionStateName.SIGN_IMAGES: {SessionStateName.FLASH_PREP, SessionStateName.BLOCKED},
    SessionStateName.FLASH_PREP: {
        SessionStateName.INSTALL_APPROVAL,
        SessionStateName.FLASH,
        SessionStateName.BLOCKED,
    },
    SessionStateName.INSTALL_APPROVAL: {
        SessionStateName.FLASH,
        SessionStateName.BLOCKED,
    },
    SessionStateName.FLASH: {
        SessionStateName.BOOTSTRAP_DEVICE,
        SessionStateName.POST_INSTALL_VERIFY,
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
        SessionStateName.POST_INSTALL_VERIFY,
        SessionStateName.PROMOTE,
        SessionStateName.RESTORE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.POST_INSTALL_VERIFY: {
        SessionStateName.COMPLETE,
        SessionStateName.RESTORE,
        SessionStateName.BLOCKED,
    },
    SessionStateName.COMPLETE: set(),
    SessionStateName.PROMOTE: set(),
    SessionStateName.RESTORE: {SessionStateName.ASSESS, SessionStateName.BLOCKED},
    SessionStateName.BLOCKED: {SessionStateName.ASSESS, SessionStateName.BLOCKER_CLASSIFY},
}


def is_transition_allowed(current: SessionStateName, target: SessionStateName) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
