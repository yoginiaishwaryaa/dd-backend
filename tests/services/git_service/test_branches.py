import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import subprocess
from app.services.git_service.branches import pull_branches
from app.services.git_service import create_docs_branch, commit_and_push_docs_branch

# =========== pull_branches Tests ===========


# Tests that successful branch pulling works for multiple branches
@pytest.mark.asyncio
async def test_pull_branches_success():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main", "feature-branch"]

    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns True on success
        assert result is True

        # Verify git commands were called (Expected calls- set-url, fetch, checkout main, pull main, checkout feature-branch, pull feature-branch)
        assert mock_run.call_count == 6


# Tests that branch pulling fails when repository doesn't exist
@pytest.mark.asyncio
async def test_pull_branches_repo_not_exists():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    with (
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=False),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False when repo doesn't exist
        assert result is False


# Tests that branch pulling fails with remote URL set failure
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
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False when set-url fails
        assert result is False


# Tests that branch pulling fails with fetch failure
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
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False when fetch fails
        assert result is False


# Tests that branch pulling continues with other branches upon checkout failure
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
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it still returns True (since it is supposed to continue even on failure)
        assert result is True


# Tests that branch pulling returns false on timeout
@pytest.mark.asyncio
async def test_pull_branches_timeout():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 500)),
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False on timeout
        assert result is False


# Tests that branch pulling returns false on general exception
@pytest.mark.asyncio
async def test_pull_branches_exception():
    repo_full_name = "owner/repo"
    access_token = "test_token"
    branches = ["main"]

    with (
        patch("subprocess.run", side_effect=Exception("Unexpected error")),
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify it returns False on exception
        assert result is False


# Tests that branch pulling verifies access token is in remote URL
@pytest.mark.asyncio
async def test_pull_branches_includes_access_token():
    repo_full_name = "owner/repo"
    access_token = "ghp_test_token_12345"
    branches = ["main"]

    mock_result = MagicMock()
    mock_result.returncode = 0

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("app.services.git_service.utils.settings") as mock_settings,
        patch.object(Path, "exists", return_value=True),
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await pull_branches(repo_full_name, access_token, branches)

        # Verify access token is included in the remote URL
        set_url_call = mock_run.call_args_list[0]
        assert "x-access-token" in str(set_url_call)
        assert access_token in str(set_url_call)
        assert result is True


# =========== create_docs_branch Tests ===========


# Tests that checkout docs branch is successful
@pytest.mark.asyncio
async def test_create_docs_branch_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await create_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="amr/update-auth",
            access_token="test_token",
            repo_full_name="owner/repo",
            pr_number=42,
        )

        assert result is not None
        assert result.startswith("docs/delta-fix/amr/update-auth-#42-")
        # Expected calls: set-url, fetch, checkout original, pull, checkout -b docs branch
        assert mock_run.call_count == 5


# Tests that checkout docs branch returns None when branch creation fails
@pytest.mark.asyncio
async def test_create_docs_branch_creation_failure():
    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()

        # The 5th call is checkout -b docs/drift-fix/... which should fail
        if call_count[0] == 5:
            mock_result.returncode = 1
            mock_result.stderr = (
                "fatal: A branch named 'docs/delta-fix/amr/update-auth-#42-...' already exists"
            )
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""

        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect) as mock_run,
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await create_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="amr/update-auth",
            access_token="test_token",
            repo_full_name="owner/repo",
            pr_number=42,
        )

        # Should return None on failure
        assert result is None
        # 5 calls: set-url, fetch, checkout original, pull, checkout -b (fail)
        assert mock_run.call_count == 5


# Tests that checkout docs branch returns none if repo not found
@pytest.mark.asyncio
async def test_create_docs_branch_repo_not_found():
    with (
        patch.object(Path, "exists", return_value=False),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await create_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="main",
            access_token="test_token",
            repo_full_name="owner/repo",
            pr_number=42,
        )

        assert result is None


# Tests that checkout docs branch returns none on fetch failure
@pytest.mark.asyncio
async def test_create_docs_branch_fetch_failure():
    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()
        # 1st call (set-url) succeeds, 2nd call (fetch) fails
        if call_count[0] == 2:
            mock_result.returncode = 1
            mock_result.stderr = "fatal: fetch failed"
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect),
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await create_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="main",
            access_token="test_token",
            repo_full_name="owner/repo",
            pr_number=42,
        )

        assert result is None


# Tests that checkout docs branch returns none on timeout
@pytest.mark.asyncio
async def test_create_docs_branch_timeout():
    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 500)),
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await create_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="main",
            access_token="test_token",
            repo_full_name="owner/repo",
            pr_number=42,
        )

        assert result is None


# =========== commit_and_push_docs_branch Tests ===========


# Tests that commit and push docs is successful
@pytest.mark.asyncio
async def test_commit_and_push_docs_branch_success():
    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()

        # Call 3 is diff --cached --quiet: returncode=1 means there ARE changes
        if call_count[0] == 3:
            mock_result.returncode = 1
        # Call 5 is rev-parse: return branch name
        elif call_count[0] == 5:
            mock_result.returncode = 0
            mock_result.stdout = "docs/delta-fix/amr/update-auth\n"
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""

        mock_result.stderr = ""
        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect) as mock_run,
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is True
        # Expected calls: set-url, add *.md, diff --cached, commit, rev-parse, push
        assert mock_run.call_count == 6


# Tests that commit and push docs handles nothing to commit gracefully
@pytest.mark.asyncio
async def test_commit_and_push_docs_branch_nothing_to_commit():
    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()

        # Call 3 is diff --cached --quiet: returncode=0 means NO changes
        if call_count[0] == 3:
            mock_result.returncode = 0
        else:
            mock_result.returncode = 0

        mock_result.stdout = ""
        mock_result.stderr = ""
        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect) as mock_run,
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        # Should return True (idempotent - nothing to commit is not an error)
        assert result is True
        # Should stop after diff --cached and not attempt commit or push
        assert mock_run.call_count == 3


# Tests that commit and push docs returns false on push failure
@pytest.mark.asyncio
async def test_commit_and_push_docs_branch_push_failure():
    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()

        if call_count[0] == 3:
            mock_result.returncode = 1  # changes exist
        elif call_count[0] == 5:
            mock_result.returncode = 0
            mock_result.stdout = "docs/delta-fix/main\n"
        elif call_count[0] == 6:
            # push fails
            mock_result.returncode = 1
            mock_result.stderr = "fatal: unable to push"
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""

        mock_result.stderr = getattr(mock_result, "stderr", "")
        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect),
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is False


# Tests that commit and push docs returns false if repo not found
@pytest.mark.asyncio
async def test_commit_and_push_docs_branch_repo_not_found():
    with (
        patch.object(Path, "exists", return_value=False),
        patch("app.services.git_service.utils.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is False
