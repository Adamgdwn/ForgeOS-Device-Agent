from app.core.models import SessionStateName
from app.core.state_machine import is_transition_allowed


def test_state_machine_allows_assess_to_path_select() -> None:
    assert is_transition_allowed(SessionStateName.ASSESS, SessionStateName.PATH_SELECT)


def test_state_machine_blocks_idle_to_flash() -> None:
    assert not is_transition_allowed(SessionStateName.IDLE, SessionStateName.FLASH)


def test_state_machine_allows_question_gate_to_flash_prep() -> None:
    assert is_transition_allowed(SessionStateName.QUESTION_GATE, SessionStateName.FLASH_PREP)
