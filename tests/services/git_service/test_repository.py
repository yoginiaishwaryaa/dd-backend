import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import subprocess
from app.services.git_service.repository import clone_repository, remove_cloned_repository

# =========== clone_repository Tests ===========


# Test successful repository cloning
@pytest.mark.asyncio
async def test_clone_repository_success():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    target_branch = "main"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Cloning into 'repo'..."
    mock_result.stderr = ""

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("pathlib.Path.mkdir") as mock_mkdir,
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await clone_repository(repo_full_name, access_token, target_branch)

        # Verify it returns the repository path (using Path so it works cross-platform)
        assert result is not None
        assert Path(result) == Path("/tmp/repos/owner/repo")

        # Verify mkdir was called to create owner directory
        mock_mkdir.assert_called_once()

        # Verify subprocess was called with correct git clone command
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "git"
        assert args[1] == "clone"
        assert args[2] == "--branch"
        assert args[3] == target_branch
        assert "x-access-token" in args[4]
        assert repo_full_name in args[4]


# Test repository cloning with different branch
@pytest.mark.asyncio
async def test_clone_repository_custom_branch():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    target_branch = "develop"

    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("pathlib.Path.mkdir"),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        await clone_repository(repo_full_name, access_token, target_branch)

        # Verify custom branch is used
        args = mock_run.call_args[0][0]
        assert args[3] == "develop"


# Test failure in repository cloning
@pytest.mark.asyncio
async def test_clone_repository_failure():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    target_branch = "main"

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "fatal: repository not found"

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("pathlib.Path.mkdir"),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await clone_repository(repo_full_name, access_token, target_branch)

        # Verify it returns None on failure
        assert result is None


# Test repository cloning timeout
@pytest.mark.asyncio
async def test_clone_repository_timeout():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    target_branch = "main"

    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 1000)),
        patch("pathlib.Path.mkdir"),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await clone_repository(repo_full_name, access_token, target_branch)

        # Verify it returns None on timeout
        assert result is None


# =========== remove_cloned_repository Tests ===========


# Test successful repository removal
def test_remove_cloned_repository_success():
    repo_full_name = "owner/repo"

    with (
        patch("shutil.rmtree") as mock_rmtree,
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        # Creating a real path object and mocking its exists method
        with patch.object(Path, "exists", return_value=True):
            result = remove_cloned_repository(repo_full_name)

        # Verify it returns True on success
        assert result is True

        # Verify rmtree was called
        mock_rmtree.assert_called_once()


# Test repository removal when path doesn't exist
def test_remove_cloned_repository_not_exists():
    repo_full_name = "owner/repo"

    with (
        patch("shutil.rmtree") as mock_rmtree,
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        # Mock exists to return False
        with patch.object(Path, "exists", return_value=False):
            result = remove_cloned_repository(repo_full_name)

        # Verify it returns False when path doesn't exist
        assert result is False

        # Verify rmtree was not called
        mock_rmtree.assert_not_called()
