import os
import re
import json
import base64
import requests
import urllib.parse
import time
import html
from bs4 import BeautifulSoup

# ================= تنظیمات =================
SOURCE_CHANNELS = ['AR14N24B', 'MTPROTO_PROXY01', 'NormanV2ray'] 
CHANNEL_ID = "VPNine1" 
V2RAY_CHUNK_SIZE = 30    # تعداد کانفیگ در هر پیام
MTPROTO_CHUNK_SIZE = 10  
DELAY_BETWEEN_MSGS = 30  

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TARGET_CHANNEL = os.environ.get('TARGET_CHANNEL')
# ===========================================

HISTORY_FILE = 'history.txt'

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return set(f.read().splitlines())
    return set()

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(list(history)[-3000:]))

def update_remark(config, remark):
    if config.startswith('vmess://'):
        try:
            b64_str = config[8:]
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            decoded = base64.b64decode(b64_str).decode('utf-8')
            data = json.loads(decoded)
            data['ps'] = remark
            new_b64 = base64.b64encode(json.dumps(data).encode('utf-8')).decode('utf-8')
            return f"vmess://{new_b64}"
        except Exception:
            return config
    else:
        if '#' in config: config = config.split('#')[0]
        # در اینجا urllib.parse.quote حذف شد تا ایموجی و متن خام بماند
        return f"{config.rstrip(')')}#{remark}"

def fetch_raw_configs():
    v2ray_links, mtproto_links = set(), set()
    pattern_v2ray = r'(?:vless|vmess|trojan|ss|ssr|tuic|hysteria2?)://[^\s"\'<>\n]+'
    pattern_tg = r'(?:https?://t\.me/proxy\?[^\s"\'<>\n]+|tg://proxy\?[^\s"\'<>\n]+)'
    
    for channel in SOURCE_CHANNELS:
        try:
            url = f"https://t.me/s/{channel}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message_text')
                for msg in messages:
                    text = msg.get_text(separator=' ')
                    for c in re.findall(pattern_v2ray, text): v2ray_links.add(c)
                    for c in re.findall(pattern_tg, text): mtproto_links.add(c)
        except Exception as e:
            print(f"Error fetching from {channel}: {e}")
    return list(v2ray_links), list(mtproto_links)

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TARGET_CHANNEL,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        print(f"Telegram API Error: {resp.text}")

def main():
    if not BOT_TOKEN or not TARGET_CHANNEL:
        print("Error: Missing credentials.")
        return

    history = load_history()
    new_v2ray, new_mtproto = fetch_raw_configs()
    
    valid_v2ray = []
    valid_mtproto = []

    for link in new_v2ray:
        base = link.split('#')[0] if not link.startswith('vmess') else link
        if base not in history:
            valid_v2ray.append(link)
            history.add(base)
            
    for link in new_mtproto:
        if link not in history:
            valid_mtproto.append(link)
            history.add(link)

    total_sent = 0

    # ================= پردازش و ارسال V2Ray =================
    for i in range(0, len(valid_v2ray), V2RAY_CHUNK_SIZE):
        chunk = valid_v2ray[i:i + V2RAY_CHUNK_SIZE]
        
        # هدر جدید، لوکس و اعتماد ساز
        msg = "<b>💎 Premium V2Ray Servers</b>\n"
        msg += "<i>✅ Checked & High-Speed</i>\n\n"
        
        msg += "<blockquote expandable>\n"
        for link in chunk:
            updated_link = update_remark(link, f"🚀@{CHANNEL_ID}")
            escaped_link = html.escape(updated_link)
            msg += f"<code>{escaped_link}</code>\n\n"
        msg += "</blockquote>\n"
        
        # فوتر پیام با هشتگ‌های ترند و دعوت به اقدام (CTA) قدرتمند
        msg += "<i>💡 برای اتصال، متن بالا را کپی کرده و در برنامه وارد کنید.</i>\n\n"
        msg += "🌐 #v2ray #vless #vmess #proxy #فیلترشکن_رایگان #پروکسی\n"
        msg += f"🛡 <b>Join Securely:</b> @{CHANNEL_ID}"
        
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + V2RAY_CHUNK_SIZE < len(valid_v2ray) or valid_mtproto:
            print(f"Sent {len(chunk)} V2ray configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    # ================= پردازش و ارسال پروکسی تلگرام =================
    for i in range(0, len(valid_mtproto), MTPROTO_CHUNK_SIZE):
        chunk = valid_mtproto[i:i + MTPROTO_CHUNK_SIZE]
        
        msg = "<b>🛡 Premium MTProto Proxies</b>\n"
        msg += "<i>⚡️ Anti-Filter Telegram</i>\n\n"
        
        # قرار دادن لینک‌های پروکسی داخل یک کوت ساده برای ظاهر تمیزتر
        msg += "<blockquote>\n"
        for idx, link in enumerate(chunk, 1):
            escaped_link = html.escape(link)
            msg += f"🔹 <a href='{escaped_link}'>Connect to Proxy {idx}</a>\n"
        msg += "</blockquote>\n"
            
        msg += "🌐 #mtproto #telegram_proxy #پروکسی_تلگرام\n"
        msg += f"🛡 <b>Join Securely:</b> @{CHANNEL_ID}"
        
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + MTPROTO_CHUNK_SIZE < len(valid_mtproto):
            print(f"Sent {len(chunk)} MTProto configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    save_history(history)
    print(f"Process finished. Successfully sent {total_sent} new configs.")

if __name__ == '__main__':
    main()
