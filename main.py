import os
import re
import json
import base64
import requests
import urllib.parse
import time
from bs4 import BeautifulSoup

# ================= تنظیمات =================
SOURCE_CHANNELS = ['AR14N24B', 'MTPROTO_PROXY01', 'NormanV2ray'] 
CHANNEL_ID = "VPNine1" 
V2RAY_CHUNK_SIZE = 30    # کاهش به ۱۵ عدد برای جلوگیری از ارور لیمیت کاراکتر تلگرام
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

def extract_host(config):
    if config.startswith('vmess://'):
        try:
            b64_str = config[8:]
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            data = json.loads(base64.b64decode(b64_str).decode('utf-8'))
            return data.get('add') or data.get('host')
        except:
            return None
    elif 'proxy?server=' in config:
        match = re.search(r'server=([^&]+)', config)
        if match: return match.group(1)
    else:
        match = re.search(r'://(?:[^@/]+@)?([^:/?#]+)', config)
        if match: return match.group(1)
    return None

def get_country_flag(host):
    if not host: return "🌍"
    try:
        clean_host = host.split(':')[0]
        resp = requests.get(f"http://ip-api.com/json/{clean_host}?fields=countryCode", timeout=5)
        if resp.status_code == 200:
            cc = resp.json().get('countryCode')
            if cc:
                return chr(ord(cc[0].upper()) + 127397) + chr(ord(cc[1].upper()) + 127397)
    except:
        pass
    return "🌍"

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
        return f"{config.rstrip(')')}#{urllib.parse.quote(remark)}"

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
    requests.post(url, json=payload)

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
        msg = "<b>New Proxies Available ⚡️</b>\n\n"
        
        for link in chunk:
            host = extract_host(link)
            flag = get_country_flag(host)
            updated_link = update_remark(link, f"🚀@{CHANNEL_ID} - {flag}")
            # استفاده از نقل‌قول جمع‌شونده به همراه تگ کپی
            msg += f"<blockquote expandable><code>{updated_link}</code></blockquote>\n"
            time.sleep(1.2) 
            
        msg += f"\n🆔 @{CHANNEL_ID}"
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + V2RAY_CHUNK_SIZE < len(valid_v2ray) or valid_mtproto:
            print(f"Sent {len(chunk)} V2ray configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    # ================= پردازش و ارسال پروکسی تلگرام =================
    for i in range(0, len(valid_mtproto), MTPROTO_CHUNK_SIZE):
        chunk = valid_mtproto[i:i + MTPROTO_CHUNK_SIZE]
        msg = "<b>New MTProto Proxies 🛡</b>\n\n"
        
        for idx, link in enumerate(chunk, 1):
            host = extract_host(link)
            flag = get_country_flag(host)
            msg += f"🔹 <a href='{link}'>Proxy {idx} - {flag}</a>\n"
            time.sleep(1.2)
            
        msg += f"\n🆔 @{CHANNEL_ID}"
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + MTPROTO_CHUNK_SIZE < len(valid_mtproto):
            print(f"Sent {len(chunk)} MTProto configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    save_history(history)
    print(f"Process finished. Successfully sent {total_sent} new configs.")

if __name__ == '__main__':
    main()
