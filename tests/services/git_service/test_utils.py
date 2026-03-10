from unittest.mock import patch
from pathlib import Path
from app.services.git_service.utils import get_local_repo_path

# =========== get_local_repo_path Tests ===========


# Test returns correct path for a standard repo full name
def test_get_local_repo_path_standard():
    with patch("app.services.git_service.utils.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"
        result = get_local_repo_path("owner/repo")
        assert result == Path("/tmp/repos/owner/repo")


# Test returns correct path with nested-style owner name
def test_get_local_repo_path_preserves_names():
    with patch("app.services.git_service.utils.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"
        result = get_local_repo_path("my-org/my-project")
        assert result == Path("/tmp/repos/my-org/my-project")


# Test returns a Path object, not a string
def test_get_local_repo_path_returns_path_object():
    with patch("app.services.git_service.utils.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"
        result = get_local_repo_path("owner/repo")
        assert isinstance(result, Path)


# Test uses the configured REPOS_BASE_PATH
def test_get_local_repo_path_uses_configured_base():
    with patch("app.services.git_service.utils.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/custom/base/path"
        result = get_local_repo_path("owner/repo")
        assert result == Path("/custom/base/path/owner/repo")


# Test with owner/repo containing uppercase characters
def test_get_local_repo_path_case_sensitivity():
    with patch("app.services.git_service.utils.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"
        result = get_local_repo_path("MyOwner/MyRepo")
        assert result == Path("/tmp/repos/MyOwner/MyRepo")


# Test with repo name that has dots and hyphens
def test_get_local_repo_path_special_characters():
    with patch("app.services.git_service.utils.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"
        result = get_local_repo_path("owner/my-repo.js")
        assert result == Path("/tmp/repos/owner/my-repo.js")
