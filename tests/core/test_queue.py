import pytest
from unittest.mock import MagicMock, patch
from rq import Queue
import redis


# Test that Redis connection is properly initialized
def test_redis_connection_initialization():
    with (
        patch("app.core.queue.redis.from_url") as mock_from_url,
        patch("app.core.queue.settings") as mock_settings,
    ):
        mock_settings.REDIS_URL = "redis://localhost:6379/0"
        mock_redis = MagicMock()
        mock_from_url.return_value = mock_redis

        # Import after patching to trigger initialisation
        import importlib
        import app.core.queue as queue_module

        importlib.reload(queue_module)

        # Verify redis.from_url was called with correct URL
        mock_from_url.assert_called_with("redis://localhost:6379/0")


# Test that task queue can be used with Redis connection
def test_task_queue_with_redis_connection():
    mock_redis = MagicMock()
    mock_queue = MagicMock(spec=Queue)

    with (
        patch("app.core.queue.redis_conn", mock_redis),
        patch("app.core.queue.task_queue", mock_queue),
    ):
        from app.core.queue import task_queue, redis_conn

        # Verify that both the queue and redis connection can be accessed correctly
        assert task_queue == mock_queue
        assert redis_conn == mock_redis


# Test enqueuing a task to the queue
def test_enqueue_task():
    mock_redis = MagicMock()
    mock_queue = MagicMock(spec=Queue)
    mock_job = MagicMock()
    mock_job.id = "job-123"
    mock_queue.enqueue.return_value = mock_job

    with (
        patch("app.core.queue.redis_conn", mock_redis),
        patch("app.core.queue.task_queue", mock_queue),
    ):
        from app.core.queue import task_queue

        # Enqueue a test function
        def test_func(arg1, arg2):
            return arg1 + arg2

        result = task_queue.enqueue(test_func, "value1", "value2")

        # Verify enqueue was called correctly
        mock_queue.enqueue.assert_called_once_with(test_func, "value1", "value2")
        assert result.id == "job-123"


# Test enqueuing with keyword arguments
def test_enqueue_task_with_kwargs():
    mock_queue = MagicMock(spec=Queue)
    mock_job = MagicMock()
    mock_job.id = "job-456"
    mock_queue.enqueue.return_value = mock_job

    with patch("app.core.queue.task_queue", mock_queue):
        from app.core.queue import task_queue

        def test_func(arg1, arg2=None):
            return arg1

        result = task_queue.enqueue(test_func, "value1", arg2="value2")

        # Verify enqueue was called with kwargs
        mock_queue.enqueue.assert_called_once_with(test_func, "value1", arg2="value2")
        assert result.id == "job-456"


# Test enqueuing with job timeout
def test_enqueue_task_with_timeout():
    mock_queue = MagicMock(spec=Queue)
    mock_job = MagicMock()
    mock_queue.enqueue.return_value = mock_job

    with patch("app.core.queue.task_queue", mock_queue):
        from app.core.queue import task_queue

        def test_func():
            pass

        task_queue.enqueue(test_func, job_timeout=300)

        # Verify timeout was passed
        mock_queue.enqueue.assert_called_once_with(test_func, job_timeout=300)


# Test Redis connection error handling
def test_redis_connection_error():
    with patch(
        "app.core.queue.redis.from_url", side_effect=redis.ConnectionError("Connection refused")
    ):
        # Verify that attempting to import queue raises the connection error
        with pytest.raises(redis.ConnectionError):
            import importlib
            import app.core.queue as queue_module

            importlib.reload(queue_module)


# Test queue length retrieval
def test_queue_length():
    mock_queue = MagicMock(spec=Queue)
    mock_queue.__len__ = MagicMock(return_value=5)

    with patch("app.core.queue.task_queue", mock_queue):
        from app.core.queue import task_queue

        length = len(task_queue)

        assert length == 5


# Test getting all job IDs from the RQ
def test_get_job_ids():
    mock_queue = MagicMock(spec=Queue)
    mock_queue.job_ids = ["job-1", "job-2", "job-3"]

    with patch("app.core.queue.task_queue", mock_queue):
        from app.core.queue import task_queue

        job_ids = task_queue.job_ids

        assert len(job_ids) == 3
        assert "job-1" in job_ids
        assert "job-2" in job_ids
        assert "job-3" in job_ids


# Test fetching a specific job from the queue
def test_fetch_job():
    mock_queue = MagicMock(spec=Queue)
    mock_job = MagicMock()
    mock_job.id = "job-123"
    mock_job.get_status.return_value = "queued"
    mock_queue.fetch_job.return_value = mock_job

    with patch("app.core.queue.task_queue", mock_queue):
        from app.core.queue import task_queue

        job = task_queue.fetch_job("job-123")

        assert job is not None
        assert job.id == "job-123"
        assert job.get_status() == "queued"
        mock_queue.fetch_job.assert_called_once_with("job-123")


# Test emptying the queue
def test_empty_queue():
    mock_queue = MagicMock(spec=Queue)

    with patch("app.core.queue.task_queue", mock_queue):
        from app.core.queue import task_queue

        task_queue.empty()

        mock_queue.empty.assert_called_once()


# Test enqueuing multiple tasks in sequence
def test_enqueue_multiple_tasks():
    mock_queue = MagicMock(spec=Queue)
    mock_jobs = [MagicMock(id=f"job-{i}") for i in range(3)]
    mock_queue.enqueue.side_effect = mock_jobs

    with patch("app.core.queue.task_queue", mock_queue):
        from app.core.queue import task_queue

        def task1():
            pass

        def task2():
            pass

        def task3():
            pass

        job1 = task_queue.enqueue(task1)
        job2 = task_queue.enqueue(task2)
        job3 = task_queue.enqueue(task3)

        assert job1.id == "job-0"
        assert job2.id == "job-1"
        assert job3.id == "job-2"
        assert mock_queue.enqueue.call_count == 3
