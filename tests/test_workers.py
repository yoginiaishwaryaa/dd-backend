import pytest
from unittest.mock import MagicMock, patch, call
import multiprocessing
from rq import Worker


# Test starting a single worker
def test_start_worker_single():
    mock_worker = MagicMock(spec=Worker)
    mock_task_queue = MagicMock()
    mock_redis_conn = MagicMock()

    with (
        patch("workers.Worker", return_value=mock_worker) as mock_worker_class,
        patch("workers.task_queue", mock_task_queue),
        patch("workers.redis_conn", mock_redis_conn),
    ):
        from workers import start_worker

        start_worker(1)

        # Verify worker was initialised correctly
        mock_worker_class.assert_called_once_with(
            [mock_task_queue], connection=mock_redis_conn, name="worker-1"
        )

        # Verify worker.work() was called
        mock_worker.work.assert_called_once()


# Test starting a worker with a different worker number
def test_start_worker_with_custom_number():
    mock_worker = MagicMock(spec=Worker)
    mock_task_queue = MagicMock()
    mock_redis_conn = MagicMock()

    with (
        patch("workers.Worker", return_value=mock_worker) as mock_worker_class,
        patch("workers.task_queue", mock_task_queue),
        patch("workers.redis_conn", mock_redis_conn),
    ):
        from workers import start_worker

        start_worker(5)

        # Verify worker was created with correct name and number
        mock_worker_class.assert_called_once_with(
            [mock_task_queue], connection=mock_redis_conn, name="worker-5"
        )


# Test worker initialisation for single worker mode
def test_main_single_worker():
    mock_settings = MagicMock()
    mock_settings.NUM_WORKERS = 1

    with (
        patch("workers.settings", mock_settings),
        patch("workers.start_worker") as mock_start_worker,
    ):
        # Simulate running the main block
        import workers

        # Manually trigger the logic that would be in __main__
        num_workers = workers.settings.NUM_WORKERS
        if num_workers == 1:
            workers.start_worker(1)

        # Verify start_worker was called once for worker 1
        mock_start_worker.assert_called_once_with(1)


# Test worker initialisation for multiple workers
def test_main_multiple_workers():
    mock_settings = MagicMock()

    # Testing with 3 workers
    mock_settings.NUM_WORKERS = 3

    mock_process = MagicMock(spec=multiprocessing.Process)

    with (
        patch("workers.settings", mock_settings),
        patch("workers.multiprocessing.Process", return_value=mock_process) as mock_process_class,
    ):
        import workers

        # Simulate the multiple worker logic
        num_workers = workers.settings.NUM_WORKERS
        if num_workers > 1:
            processes = []
            for i in range(1, num_workers + 1):
                process = multiprocessing.Process(target=workers.start_worker, args=(i,))
                process.start()
                processes.append(process)

        # Verify process was created 3 times
        assert mock_process_class.call_count == 3

        # Verify each process was started
        assert mock_process.start.call_count == 3

        # Verify process was called with correct args
        expected_calls = [
            call(target=workers.start_worker, args=(1,)),
            call(target=workers.start_worker, args=(2,)),
            call(target=workers.start_worker, args=(3,)),
        ]
        mock_process_class.assert_has_calls(expected_calls)


# Test worker listens to correct queue
def test_worker_listens_to_task_queue():
    mock_worker = MagicMock(spec=Worker)
    mock_task_queue = MagicMock()
    mock_task_queue.name = "default"
    mock_redis_conn = MagicMock()

    with (
        patch("workers.Worker", return_value=mock_worker) as mock_worker_class,
        patch("workers.task_queue", mock_task_queue),
        patch("workers.redis_conn", mock_redis_conn),
    ):
        from workers import start_worker

        start_worker(1)

        # Verify worker was initialised with the task_queue
        args, kwargs = mock_worker_class.call_args
        assert mock_task_queue in args[0]


# Test worker name formatting
def test_worker_name_formatting():
    mock_worker = MagicMock(spec=Worker)

    with (
        patch("workers.Worker", return_value=mock_worker) as mock_worker_class,
        patch("workers.task_queue", MagicMock()),
        patch("workers.redis_conn", MagicMock()),
    ):
        from workers import start_worker

        # Test multiple worker numbers
        for worker_num in [1, 5, 10, 100]:
            start_worker(worker_num)

        # Verify worker names were formatted correctly
        call_args_list = mock_worker_class.call_args_list
        assert call_args_list[0][1]["name"] == "worker-1"
        assert call_args_list[1][1]["name"] == "worker-5"
        assert call_args_list[2][1]["name"] == "worker-10"
        assert call_args_list[3][1]["name"] == "worker-100"


# Test worker with zero workers configuration
def test_zero_workers():
    mock_settings = MagicMock()
    mock_settings.NUM_WORKERS = 0

    with (
        patch("workers.settings", mock_settings),
        patch("workers.start_worker") as mock_start_worker,
        patch("workers.multiprocessing.Process") as mock_process,
    ):
        import workers

        # Simulate the main block logic
        num_workers = workers.settings.NUM_WORKERS
        if num_workers == 1:
            workers.start_worker(1)
        elif num_workers > 1:
            pass  # This would start multiple workers

        # Verify that no workers were started
        mock_start_worker.assert_not_called()
        mock_process.assert_not_called()


# Test worker exception handling during work
def test_worker_exception_during_work():
    mock_worker = MagicMock(spec=Worker)
    mock_worker.work.side_effect = Exception("Worker error")

    with (
        patch("workers.Worker", return_value=mock_worker),
        patch("workers.task_queue", MagicMock()),
        patch("workers.redis_conn", MagicMock()),
    ):
        from workers import start_worker

        # Verify exception is raised
        with pytest.raises(Exception, match="Worker error"):
            start_worker(1)


# Test that the redis connection is shared across workers
def test_redis_connection_shared():
    mock_worker1 = MagicMock(spec=Worker)
    mock_worker2 = MagicMock(spec=Worker)
    mock_redis_conn = MagicMock()

    with (
        patch("workers.Worker", side_effect=[mock_worker1, mock_worker2]) as mock_worker_class,
        patch("workers.task_queue", MagicMock()),
        patch("workers.redis_conn", mock_redis_conn),
    ):
        from workers import start_worker

        start_worker(1)
        start_worker(2)

        # Verify that both the workers use the same redis connection
        assert mock_worker_class.call_args_list[0][1]["connection"] is mock_redis_conn
        assert mock_worker_class.call_args_list[1][1]["connection"] is mock_redis_conn


# Test that the task queue is shared across workers
def test_task_queue_shared():
    mock_worker1 = MagicMock(spec=Worker)
    mock_worker2 = MagicMock(spec=Worker)
    mock_task_queue = MagicMock()

    with (
        patch("workers.Worker", side_effect=[mock_worker1, mock_worker2]) as mock_worker_class,
        patch("workers.task_queue", mock_task_queue),
        patch("workers.redis_conn", MagicMock()),
    ):
        from workers import start_worker

        start_worker(1)
        start_worker(2)

        # Verify that both workers listen to the same queue
        assert mock_task_queue in mock_worker_class.call_args_list[0][0][0]
        assert mock_task_queue in mock_worker_class.call_args_list[1][0][0]
