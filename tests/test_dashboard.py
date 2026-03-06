import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.routers.dashboard import get_dashboard_stats, get_dashboard_repos


# Test fixtures for mocking user and database
@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    return user


@pytest.fixture
def mock_db():
    return MagicMock()


# Test that dashboard stats returns correct counts
def test_get_dashboard_stats(mock_db, mock_user):
    query_mock = mock_db.query.return_value
    _ = query_mock.filter.return_value
    _ = query_mock.join.return_value

    # Mock the count queries to return specific values
    mock_db.query.return_value.filter.return_value.scalar.side_effect = [5]
    mock_db.query.return_value.join.return_value.filter.return_value.scalar.side_effect = [12]
    mock_db.query.return_value.join.return_value.join.return_value.filter.return_value.scalar.side_effect = [
        3
    ]
    q = mock_db.query.return_value

    q.filter.return_value.scalar.return_value = 5  # 5 installations

    q.join.return_value.filter.return_value.scalar.return_value = 12  # 12 linked repos

    q.join.return_value.join.return_value.filter.return_value.scalar.return_value = (
        3  # 3 drift events
    )

    stats = get_dashboard_stats(mock_db, mock_user)

    # Verify all counts are returned correctly
    assert stats["installations_count"] == 5
    assert stats["repos_linked_count"] == 12
    assert stats["drift_events_count"] == 3
    assert stats["pr_waiting_count"] == 0


# Test that dashboard repos fetches and returns repo details from github
@pytest.mark.asyncio
async def test_get_dashboard_repos(mock_db, mock_user):
    # Setup mock repos
    repo1 = MagicMock()
    repo1.repo_name = "owner/repo1"
    repo1.installation_id = 101

    repo2 = MagicMock()
    repo2.repo_name = "owner/repo2"
    repo2.installation_id = 102

    # Mock the DB query to return the test repos
    mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        repo1,
        repo2,
    ]

    # Mock the GH API call
    with patch("app.routers.dashboard.get_repo_details", new_callable=AsyncMock) as mock_service:
        mock_service.return_value = {
            "name": "mock-repo",
            "description": "desc",
            "language": "python",
            "stargazers_count": 10,
            "forks_count": 2,
        }

        results = await get_dashboard_repos(mock_db, mock_user)

        # Verify results for both repos
        assert len(results) == 2
        assert results[0]["name"] == "mock-repo"
        assert mock_service.call_count == 2
