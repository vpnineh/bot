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
V2RAY_CHUNK_SIZE = 15    # حتماً روی ۱۵ بماند تا ارور لیمیت کاراکتر تلگرام ندهد
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
                    # ۱. استخراج پروکسی‌های عادی از متن
                    text = msg.get_text(separator=' ')
                    for c in re.findall(pattern_v2ray, text): v2ray_links.add(c)
                    for c in re.findall(pattern_tg, text): mtproto_links.add(c)
                    
                    # ۲. استخراج پروکسی‌های مخفی در لینک‌های شیشه‌ای (href)
                    for a_tag in msg.find_all('a'):
                        href = a_tag.get('href')
                        if href:
                            for c in re.findall(pattern_v2ray, href): v2ray_links.add(c)
                            for c in re.findall(pattern_tg, href): mtproto_links.add(c)
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

    # ================= UI حرفه‌ای V2Ray =================
    for i in range(0, len(valid_v2ray), V2RAY_CHUNK_SIZE):
        chunk = valid_v2ray[i:i + V2RAY_CHUNK_SIZE]
        
        msg = "<b>💎 Premium V2Ray Servers</b>\n"
        msg += "<i>✅ Checked & High-Speed</i>\n\n"
        
        msg += "👇 <i>جهت کپی کل لیست، روی کادر ضربه بزنید:</i>\n"
        
        # باز کردن کوت جمع شونده
        msg += "<blockquote expandable>"
        
        # باز کردن یک تگ کدِ واحد برای کل لینک‌ها تا با هم کپی شوند
        msg += "<code>"
        all_configs = ""
        for link in chunk:
            updated_link = update_remark(link, f"🚀@{CHANNEL_ID}")
            escaped_link = html.escape(updated_link)
            # قرار دادن هر کانفیگ در یک خط جدید
            all_configs += f"{escaped_link}\n"
        
        # پاک کردن فاصله خالی خط آخر و بستن تگ کد
        msg += all_configs.strip()
        msg += "</code>\n"
        
        # بستن کوت جمع شونده
        msg += "</blockquote>\n"
        
        msg += "🌐 #v2ray #vless #vpn #config #کانفیگ\n"
        msg += f"🛡 <b>Join:</b> @{CHANNEL_ID}"
        
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + V2RAY_CHUNK_SIZE < len(valid_v2ray) or valid_mtproto:
            print(f"Sent {len(chunk)} V2ray configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    # ================= UI حرفه‌ای پروکسی تلگرام =================
    for i in range(0, len(valid_mtproto), MTPROTO_CHUNK_SIZE):
        chunk = valid_mtproto[i:i + MTPROTO_CHUNK_SIZE]
        
        msg = "<b>🛡 Premium MTProto Proxies</b>\n"
        msg += "<i>⚡️ Anti-Filter Telegram</i>\n\n"
        
        for idx, link in enumerate(chunk, 1):
            escaped_link = html.escape(link)
            msg += f"🔹 <a href='{escaped_link}'>Connect to Proxy {idx}</a>\n\n"
            
        msg += "🌐 #mtproto #proxy\n"
        msg += f"🛡 <b>Join:</b> @{CHANNEL_ID}"
        
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + MTPROTO_CHUNK_SIZE < len(valid_mtproto):
            print(f"Sent {len(chunk)} MTProto configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    save_history(history)
    print(f"Process finished. Successfully sent {total_sent} new configs.")

if __name__ == '__main__':
    main()
