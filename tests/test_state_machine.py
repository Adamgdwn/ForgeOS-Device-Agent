from app.core.models import SessionStateName
from app.core.state_machine import is_transition_allowed


def test_state_machine_allows_assess_to_path_select() -> None:
    assert is_transition_allowed(SessionStateName.ASSESS, SessionStateName.PATH_SELECT)


def test_state_machine_blocks_idle_to_flash() -> None:
    assert not is_transition_allowed(SessionStateName.IDLE, SessionStateName.FLASH)


def test_state_machine_allows_question_gate_to_flash_prep() -> None:
    assert is_transition_allowed(SessionStateName.QUESTION_GATE, SessionStateName.FLASH_PREP)


def test_state_machine_allows_question_gate_resume_into_runtime() -> None:
    assert is_transition_allowed(SessionStateName.QUESTION_GATE, SessionStateName.BACKUP_READY)
    assert is_transition_allowed(SessionStateName.BACKUP_READY, SessionStateName.ITERATE)
    assert is_transition_allowed(SessionStateName.BACKUP_READY, SessionStateName.BUILD_GENERIC)


def test_state_machine_allows_remediation_loop() -> None:
    assert is_transition_allowed(SessionStateName.BLOCKER_CLASSIFY, SessionStateName.REMEDIATION_DECIDE)
    assert is_transition_allowed(SessionStateName.REMEDIATION_DECIDE, SessionStateName.TASK_CREATE)
    assert is_transition_allowed(SessionStateName.TASK_CREATE, SessionStateName.CODEGEN_WRITE)
    assert is_transition_allowed(SessionStateName.CODEGEN_WRITE, SessionStateName.PATCH_APPLY)
    assert is_transition_allowed(SessionStateName.PATCH_APPLY, SessionStateName.EXECUTE_ARTIFACT)
    assert is_transition_allowed(SessionStateName.EXECUTE_ARTIFACT, SessionStateName.INSPECT_RESULT)


def test_state_machine_allows_runtime_first_device_flow() -> None:
    assert is_transition_allowed(SessionStateName.DEVICE_ATTACHED, SessionStateName.INTAKE)
    assert is_transition_allowed(SessionStateName.INTAKE, SessionStateName.ACCESS_ENABLEMENT)
    assert is_transition_allowed(SessionStateName.ACCESS_ENABLEMENT, SessionStateName.DEEP_SCAN)
    assert is_transition_allowed(SessionStateName.ASSESS, SessionStateName.RECOMMEND)
    assert is_transition_allowed(SessionStateName.BACKUP_PLAN, SessionStateName.BACKUP_READY)
    assert is_transition_allowed(SessionStateName.PREVIEW_BUILD, SessionStateName.PREVIEW_REVIEW)
    assert is_transition_allowed(SessionStateName.INTERACTIVE_VERIFY, SessionStateName.INSTALL_APPROVAL)
    assert is_transition_allowed(SessionStateName.FLASH, SessionStateName.POST_INSTALL_VERIFY)
