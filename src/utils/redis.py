import os
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

def get_redis_client():
    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

    if not redis_url or not redis_token:
        raise ValueError("Thiếu biến môi trường UPSTASH_REDIS_REST_URL hoặc UPSTASH_REDIS_REST_TOKEN")

    redis_url = redis_url.strip('"').strip("'")
    redis_token = redis_token.strip('"').strip("'")

    client = Redis(url=redis_url, token=redis_token)
    return client

def get_redis_key(user_id: str, conv_id: int, suffix: str = 'messages') -> str:

    return f"user:{user_id}:conv:{conv_id}:{suffix}"

# if __name__ == "__main__":
#     r = get_redis_client()
#     r.set("test_key", "Hello Upstash Redis!")
#     print("test_key =", r.get("test_key"))
