"""Gunicorn loads this file from the repository working directory by default."""


def post_worker_init(worker):
    # Start after fork: never create DB/network threads in the Gunicorn master.
    from src.workers.ingestion import start_worker_thread
    thread = start_worker_thread()
    if thread is not None:
        worker.log.info('Embedded document ingestion worker started')


def worker_exit(server, worker):
    from src.workers.ingestion import stop_worker_thread
    stop_worker_thread()
