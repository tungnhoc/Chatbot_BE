from gradio_client import Client

_client = None

def get_client():
    global _client
    if _client is None:
        # Load the client only when the function is first called, 
        # so intermittent HuggingFace timeouts don't crash the server startup.
        _client = Client("hung102004/Demo-SecurePass")
    return _client

def predict_password_strength(password: str) -> str:
    try:
        client = get_client()
        result = client.predict(
            password=password,
            api_name="/predict_ui"
        )
        return result["label"]
    except Exception as e:
        print(f"Error calling password strength API: {e}")
        # Mặc định an toàn nếu API HuggingFace bị sập
        return "Unknown"
