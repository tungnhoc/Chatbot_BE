from groq import Groq, RateLimitError
import os
from dotenv import load_dotenv
load_dotenv()
import time
import logging


import re
from contextvars import ContextVar
from threading import Lock

_last_usage = ContextVar('groq_usage', default=None)

_pace_lock = Lock()
_next_request_at = 0.0

class LanguageModelUnavailable(RuntimeError):
    pass

class LanguageModelRateLimited(LanguageModelUnavailable):
    pass

def _create_completion(client, **options):
    global _next_request_at
    for attempt in range(3):
        interval = float(os.getenv('GROQ_REQUEST_INTERVAL', '0'))
        with _pace_lock:
            wait = max(0, _next_request_at - time.monotonic())
            _next_request_at = max(_next_request_at, time.monotonic()) + interval
        if wait:
            time.sleep(wait)
        try:
            return client.chat.completions.create(**options)
        except RateLimitError as error:
            if attempt == 2:
                raise
            raw = error.response.headers.get('retry-after', '5')
            try:
                delay = float(raw)
            except ValueError:
                delay = 5
            time.sleep(max(1, min(delay, 30)))



def get_last_usage():
    return _last_usage.get()

def clean_llm_response(text: str) -> str:
    if not text:
        return ""
    # Remove completed <think>...</think> tags
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # If <think> tag was not closed (e.g. truncated response), remove from <think> to end
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()

def generate_groq_response(prompt: str) -> str:
   _last_usage.set(None)
   start = time.time()
   api_key = os.getenv("GROQ_API_KEY")
   

   if not api_key:
      raise ValueError("❌ Không tìm thấy GROQ_API_KEY trong file .env")
   
   client = Groq(api_key=api_key, timeout=60.0, max_retries=2)

   try:
      model_name = (os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b")
      response = _create_completion(client,
            model=model_name,
            messages=[
                
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=float(os.getenv('LLM_TEMPERATURE', '0.2')),
            max_tokens=2048       
        )

      logging.getLogger(__name__).info('Groq request completed in %.2fs', time.time() - start)
      raw_content = response.choices[0].message.content or ""
      if response.usage:
         _last_usage.set(response.usage.model_dump())
      cleaned = clean_llm_response(raw_content)
      if not cleaned:
         raise RuntimeError('Language model returned an empty answer')
      return cleaned

   except Exception as e:
        logging.getLogger(__name__).warning('Groq request failed: %s', type(e).__name__)
        if isinstance(e, RateLimitError):
            raise LanguageModelRateLimited("AI service rate limit reached; please try again shortly") from e
        raise LanguageModelUnavailable("Language model request failed") from e




if __name__ == "__main__":

    prompt = """
hello
"""

    # 🚀 Gọi hàm sinh tóm tắt
    summary = generate_groq_response(prompt)
    print("📘 Tóm tắt hội thoại:\n")
    print(summary)
    

