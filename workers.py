import multiprocessing
from rq import Worker
from app.core.queue import redis_conn, task_queue
from app.core.config import settings


# Start a single RQ worker process with a worker_num that listens to the task queue
def start_worker(worker_num: int):
    worker = Worker([task_queue], connection=redis_conn, name=f"worker-{worker_num}")
    print(f"Worker {worker_num} started... Listening for tasks...")
    worker.work()


if __name__ == "__main__":
    # Read the number of workers to start from settings
    num_workers = settings.NUM_WORKERS
    print(f"Starting {num_workers} RQ worker(s)...")

    if num_workers == 1:
        # If num_workers = 1, then start a single worker in the main process
        start_worker(1)
    else:
        # Else, start multiple workers using multiprocessing
        processes = []
        for i in range(1, num_workers + 1):
            process = multiprocessing.Process(target=start_worker, args=(i,))
            process.start()
            processes.append(process)

        # Wait for all worker processes to finish
        for process in processes:
            process.join()
