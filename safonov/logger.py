import requests
import config

def send_tg_log(message: str):
    if not config.TG_BOT_TOKEN or not config.TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{config.TG_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": config.TG_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data, timeout=10)  # было 3
    except Exception as e:
        print(f"TG log error: {e}")