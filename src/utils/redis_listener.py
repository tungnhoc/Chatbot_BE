import time
from threading import Thread
from src.utils.redis import get_redis_client, get_redis_key
from src.config.db_session import SessionLocal
from src.services.chat_service import finalize_conversation

CHECK_INTERVAL = 5


def redis_expire_watcher():
    print("Redis TTL watcher started...")
    logged_error = False

    while True:
        try:
            client = get_redis_client()
            keys = client.keys("user:*:conv:*:messages")

            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()

                ttl = client.ttl(key)
                print(f"Checking key {key}, TTL={ttl}s")

                if ttl <= 5 and ttl != -1:
                    lock_key = f"{key}:lock"

                    if not client.set(lock_key, "1", nx=True, ex=60):
                        print(f" Skip finalize (locked): {key}")
                        continue

                    parts = key.split(":")
                    user_id = parts[1]
                    conv_id = int(parts[3])

                    print(f"TTL expired → Finalizing conversation {conv_id}")

                    session = SessionLocal()
                    try:
                        finalize_conversation(session, user_id, conv_id)
                        print(f"Finalized conversation {conv_id}")
                    except Exception as e:
                        print(f"Error finalizing conv {conv_id}: {e}")
                    finally:
                        session.close()

                    client.delete(key)

            logged_error = False
        except Exception as e:
            if not logged_error:
                print("⚠️ Upstash Redis API đã hết hạn hoặc không thể kết nối. Hệ thống tự động chuyển sang dùng MySQL trực tiếp.")
                logged_error = True
            time.sleep(30)
            continue

        time.sleep(CHECK_INTERVAL)


def start_redis_watcher_thread():
    Thread(target=redis_expire_watcher, daemon=True).start()
