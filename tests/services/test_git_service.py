import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import subprocess
from app.services.git_service import (
    clone_repository,
    remove_cloned_repository,
    pull_branches,
    get_local_repo_path,
)


# Test returns correct path for a standard repo full name
def test_get_local_repo_path_standard():
    with patch("app.services.git_service.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = get_local_repo_path("owner/repo")

        assert result == Path("/tmp/repos/owner/repo")


# Test returns correct path with nested-style owner name
def test_get_local_repo_path_preserves_names():
    with patch("app.services.git_service.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = get_local_repo_path("my-org/my-project")

        assert result == Path("/tmp/repos/my-org/my-project")


# Test returns a Path object, not a string
def test_get_local_repo_path_returns_path_object():
    with patch("app.services.git_service.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = get_local_repo_path("owner/repo")

        assert isinstance(result, Path)


# Test uses the configured REPOS_BASE_PATH
def test_get_local_repo_path_uses_configured_base():
    with patch("app.services.git_service.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/custom/base/path"

        result = get_local_repo_path("owner/repo")

        assert result == Path("/custom/base/path/owner/repo")


# Test with owner/repo containing uppercase characters
def test_get_local_repo_path_case_sensitivity():
    with patch("app.services.git_service.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = get_local_repo_path("MyOwner/MyRepo")

        # Should preserve case as-is
        assert result == Path("/tmp/repos/MyOwner/MyRepo")


# Test with repo name that has dots and hyphens
def test_get_local_repo_path_special_characters():
    with patch("app.services.git_service.settings") as mock_settings:
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = get_local_repo_path("owner/my-repo.js")

        assert result == Path("/tmp/repos/owner/my-repo.js")


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
        patch("app.services.git_service.settings") as mock_settings,
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
        patch("app.services.git_service.settings") as mock_settings,
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
        patch("app.services.git_service.settings") as mock_settings,
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
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await clone_repository(repo_full_name, access_token, target_branch)

        # Verify it returns None on timeout
        assert result is None


# Test successful repository removal
def test_remove_cloned_repository_success():
    repo_full_name = "owner/repo"

    with (
        patch("shutil.rmtree") as mock_rmtree,
        patch("app.services.git_service.settings") as mock_settings,
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
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        # Mock exists to return False
        with patch.object(Path, "exists", return_value=False):
            result = remove_cloned_repository(repo_full_name)

        # Verify it returns False when path doesn't exist
        assert result is False

        # Verify rmtree was not called
        mock_rmtree.assert_not_called()


# Test successful branch pulling for multiple branches
@pytest.mark.asyncio
async def test_pull_branches_success():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main", "feature-branch"]

    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns True on success
        assert result is True

        # Verify git commands were called (Expected calls- set-url, fetch, checkout main, pull main, checkout feature-branch, pull feature-branch)
        assert mock_run.call_count == 6


# Test branch pulling when repository doesn't exist
@pytest.mark.asyncio
async def test_pull_branches_repo_not_exists():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    with (
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=False),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False when repo doesn't exist
        assert result is False


# Test branch pulling with remote URL set failure
@pytest.mark.asyncio
async def test_pull_branches_set_url_failure():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "fatal: No such remote 'origin'"

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False when set-url fails
        assert result is False


# Test branch pulling with fetch failure
@pytest.mark.asyncio
async def test_pull_branches_fetch_failure():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    def mock_run_side_effect(*args, **kwargs):
        mock_result = MagicMock()
        # First call (set-url) succeeds but second call (fetch) fails
        if "set-url" in args[0]:
            mock_result.returncode = 0
        elif "fetch" in args[0]:
            mock_result.returncode = 1
            mock_result.stderr = "fatal: couldn't find remote ref"
        else:
            mock_result.returncode = 0
        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect),
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False when fetch fails
        assert result is False


# Test branch pulling with checkout failure (should continue with other branches)
@pytest.mark.asyncio
async def test_pull_branches_checkout_failure():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["non-existent-branch", "main"]

    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        mock_result = MagicMock()
        call_count[0] += 1

        # set-url and fetch succeeds
        if "set-url" in args[0] or "fetch" in args[0]:
            mock_result.returncode = 0

        # First checkout (non-existent-branch) fails
        elif "checkout" in args[0] and call_count[0] == 3:
            mock_result.returncode = 1
            mock_result.stderr = "error: pathspec 'non-existent-branch' did not match"

        # Other commands succeed
        else:
            mock_result.returncode = 0
        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect),
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it still returns True (since it is supposed to continue even on failure)
        assert result is True


# Test branch pulling with timeout
@pytest.mark.asyncio
async def test_pull_branches_timeout():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 500)),
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False on timeout
        assert result is False


# Test branch pulling with general exception
@pytest.mark.asyncio
async def test_pull_branches_exception():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    with (
        patch("subprocess.run", side_effect=Exception("Unexpected error")),
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False on exception
        assert result is False


# Test branch pulling verifies access token is in remote URL
@pytest.mark.asyncio
async def test_pull_branches_includes_access_token():
    repo_full_name = "owner/repo"
    access_token = "ghp_test_token_12345"
    branches = ["main"]

    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("app.services.git_service.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify access token is included in the remote URL
        set_url_call = mock_run.call_args_list[0]
        assert "x-access-token" in str(set_url_call)
        assert access_token in str(set_url_call)
        assert result is True
