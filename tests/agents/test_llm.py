from unittest.mock import MagicMock, patch
from app.agents.llm import get_llm


# =========== Tests ===========


# Tests that get_llm returns a ChatGoogleGenerativeAI instance
def test_get_llm_returns_instance():
    mock_instance = MagicMock()

    with patch("app.agents.llm.ChatGoogleGenerativeAI", return_value=mock_instance) as mock_cls:
        result = get_llm()

    assert result is mock_instance
    mock_cls.assert_called_once()


# Tests that get_llm uses the default temperature of 0 when none is provided
def test_get_llm_default_temperature():
    with patch("app.agents.llm.ChatGoogleGenerativeAI") as mock_cls:
        get_llm()

    _, kwargs = mock_cls.call_args
    assert kwargs["temperature"] == 0


# Tests that get_llm forwards the provided temperature to ChatGoogleGenerativeAI
def test_get_llm_custom_temperature():
    with patch("app.agents.llm.ChatGoogleGenerativeAI") as mock_cls:
        get_llm(temperature=0.7)

    _, kwargs = mock_cls.call_args
    assert kwargs["temperature"] == 0.7


# Tests that get_llm passes the model name from settings
def test_get_llm_uses_settings_model():
    with (
        patch("app.agents.llm.ChatGoogleGenerativeAI") as mock_cls,
        patch("app.agents.llm.settings") as mock_settings,
    ):
        mock_settings.LLM_MODEL = "gemini-test-model"
        mock_settings.GEMINI_API_KEY = "test-key"
        get_llm()

    _, kwargs = mock_cls.call_args
    assert kwargs["model"] == "gemini-test-model"


# Tests that get_llm passes the API key from settings
def test_get_llm_uses_settings_api_key():
    with (
        patch("app.agents.llm.ChatGoogleGenerativeAI") as mock_cls,
        patch("app.agents.llm.settings") as mock_settings,
    ):
        mock_settings.LLM_MODEL = "gemini-test-model"
        mock_settings.GEMINI_API_KEY = "my-secret-key"
        get_llm()

    _, kwargs = mock_cls.call_args
    assert kwargs["google_api_key"] == "my-secret-key"


# Tests that each call to get_llm constructs a new instance
def test_get_llm_returns_new_instance_each_call():
    first = MagicMock()
    second = MagicMock()

    with patch("app.agents.llm.ChatGoogleGenerativeAI", side_effect=[first, second]):
        result_a = get_llm()
        result_b = get_llm()

    assert result_a is first
    assert result_b is second
    assert result_a is not result_b
