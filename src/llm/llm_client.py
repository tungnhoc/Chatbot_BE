from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()
import time


import re

def clean_llm_response(text: str) -> str:
    if not text:
        return ""
    # Remove completed <think>...</think> tags
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # If <think> tag was not closed (e.g. truncated response), remove from <think> to end
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()

def generate_groq_response(prompt: str) -> str:
   start = time.time()
   api_key = os.getenv("GROQ_API_KEY")
   

   if not api_key:
      raise ValueError("❌ Không tìm thấy GROQ_API_KEY trong file .env")
   
   client = Groq(api_key=api_key)

   try:
      model_name = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
      response = client.chat.completions.create(
            model=model_name,
            messages=[
                
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,     
            max_tokens=2048       
        )

      print(f"⏱️ Thời gian gọi Groq API: {time.time() - start:.2f} giây")
      raw_content = response.choices[0].message.content or ""
      return clean_llm_response(raw_content)

   except Exception as e:
        print("❌ Lỗi khi gọi Groq API:", e)
        return "Lỗi khi gọi mô hình."




if __name__ == "__main__":

    prompt = """
hello
"""

    # 🚀 Gọi hàm sinh tóm tắt
    summary = generate_groq_response(prompt)
    print("📘 Tóm tắt hội thoại:\n")
    print(summary)
    

