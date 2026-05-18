from app.core.model_router import ModelRouter


OLLAMA_LIST = """NAME              ID              SIZE      MODIFIED
qwen3:8b          abc123          5.2 GB    2 days ago
gemma4:latest     def456          9.6 GB    1 day ago
"""


def test_fast_triage_prefers_installed_fast_model() -> None:
    router = ModelRouter.from_ollama_list(OLLAMA_LIST, {})

    selection = router.select_for_task(
        task_type="device_discovery",
        risk="low",
        repetitive=True,
    )

    assert selection.role == "fast_triage"
    assert selection.model == "qwen3:8b"
    assert selection.available is True


def test_research_and_frontier_default_to_reasoning_model() -> None:
    router = ModelRouter.from_ollama_list(OLLAMA_LIST, {})

    research = router.select_for_task(task_type="firmware_research", risk="medium")
    frontier = router.select_for_task(task_type="install_planning", risk="high")

    assert research.role == "research"
    assert research.model == "gemma4:latest"
    assert frontier.role == "frontier"
    assert frontier.model == "gemma4:latest"


def test_fast_triage_falls_back_when_helper_model_is_missing() -> None:
    router = ModelRouter.from_ollama_list(
        """NAME              ID              SIZE      MODIFIED
gemma4:latest     def456          9.6 GB    1 day ago
""",
        {},
    )

    selection = router.select("fast_triage")

    assert selection.model == "gemma4:latest"
    assert selection.available is True
    assert selection.requested_model == "qwen3:8b"


def test_env_override_wins_when_installed() -> None:
    router = ModelRouter.from_ollama_list(
        OLLAMA_LIST,
        {"FORGEOS_FAST_MODEL": "gemma4:latest", "FORGEOS_OLLAMA_MODEL": "qwen3:8b"},
    )

    selection = router.select("fast_triage")

    assert selection.model == "gemma4:latest"
    assert selection.source == "FORGEOS_FAST_MODEL"


def test_aider_model_wraps_plain_ollama_model() -> None:
    router = ModelRouter.from_ollama_list(OLLAMA_LIST, {})

    selection = router.select("coding")

    assert selection.model == "gemma4:latest"
    assert selection.aider_model() == "ollama_chat/gemma4:latest"


def test_explicit_aider_provider_model_is_preserved() -> None:
    router = ModelRouter.from_ollama_list(
        OLLAMA_LIST,
        {"FORGEOS_AIDER_MODEL": "openai/gpt-4.1"},
    )

    selection = router.select("coding")

    assert selection.model == "openai/gpt-4.1"
    assert selection.provider == "aider"
    assert selection.aider_model() == "openai/gpt-4.1"
