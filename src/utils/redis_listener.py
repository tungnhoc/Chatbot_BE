"""Compatibility shim: durability no longer depends on a TTL watcher."""
import logging


def start_redis_watcher_thread():
    logging.getLogger(__name__).info('TTL watcher disabled; messages persist in MySQL')
