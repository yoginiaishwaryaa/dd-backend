import pytest
from unittest.mock import MagicMock

# =========== Fixtures ===========


# Test fixture for mocking DB session
@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    return session
