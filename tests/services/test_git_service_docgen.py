import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import subprocess
from app.services.git_service import checkout_docs_branch, commit_and_push_docs


# ----- checkout_docs_branch tests -----


@pytest.mark.asyncio
async def test_checkout_docs_branch_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with (
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await checkout_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="amr/update-auth",
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result == "docs/drift-fix/amr/update-auth"
        # Expected calls: set-url, fetch, checkout original, pull, checkout -b docs branch
        assert mock_run.call_count == 5


@pytest.mark.asyncio
async def test_checkout_docs_branch_already_exists_appends_timestamp():
    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()

        # The 5th call is checkout -b docs/drift-fix/... which should fail
        if call_count[0] == 5:
            mock_result.returncode = 1
            mock_result.stderr = "fatal: A branch named 'docs/drift-fix/amr/update-auth' already exists"
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""

        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect) as mock_run,
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await checkout_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="amr/update-auth",
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        # Should have appended timestamp
        assert result is not None
        assert result.startswith("docs/drift-fix/amr/update-auth-")
        # 6 calls: set-url, fetch, checkout original, pull, checkout -b (fail), checkout -b with timestamp
        assert mock_run.call_count == 6


@pytest.mark.asyncio
async def test_checkout_docs_branch_repo_not_found():
    with (
        patch.object(Path, "exists", return_value=False),
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await checkout_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="main",
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is None


@pytest.mark.asyncio
async def test_checkout_docs_branch_fetch_failure():
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
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await checkout_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="main",
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is None


@pytest.mark.asyncio
async def test_checkout_docs_branch_timeout():
    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 500)),
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await checkout_docs_branch(
            repo_path="/tmp/repos/owner/repo",
            original_branch="main",
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is None


# ----- commit_and_push_docs tests -----


@pytest.mark.asyncio
async def test_commit_and_push_docs_success():
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
            mock_result.stdout = "docs/drift-fix/amr/update-auth\n"
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""

        mock_result.stderr = ""
        return mock_result

    with (
        patch("subprocess.run", side_effect=mock_run_side_effect) as mock_run,
        patch.object(Path, "exists", return_value=True),
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is True
        # Expected calls: set-url, add *.md, diff --cached, commit, rev-parse, push
        assert mock_run.call_count == 6


@pytest.mark.asyncio
async def test_commit_and_push_docs_nothing_to_commit():
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
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        # Should return True (idempotent — nothing to commit is not an error)
        assert result is True
        # Should stop after diff --cached and not attempt commit or push
        assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_commit_and_push_docs_push_failure():
    call_count = [0]

    def mock_run_side_effect(*args, **kwargs):
        call_count[0] += 1
        mock_result = MagicMock()

        if call_count[0] == 3:
            mock_result.returncode = 1  # changes exist
        elif call_count[0] == 5:
            mock_result.returncode = 0
            mock_result.stdout = "docs/drift-fix/main\n"
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
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is False


@pytest.mark.asyncio
async def test_commit_and_push_docs_repo_not_found():
    with (
        patch.object(Path, "exists", return_value=False),
        patch("app.services.git_service.settings") as mock_settings,
    ):
        mock_settings.REPOS_BASE_PATH = "/tmp/repos"

        result = await commit_and_push_docs(
            repo_path="/tmp/repos/owner/repo",
            pr_number=42,
            access_token="test_token",
            repo_full_name="owner/repo",
        )

        assert result is False
