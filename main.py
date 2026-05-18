import os
import re
import json
import base64
import requests
import urllib.parse
import time
import html
import socket
import concurrent.futures
from bs4 import BeautifulSoup

# ================= تنظیمات =================
SOURCE_CHANNELS = ['AR14N24B', 'oneclickvpnkeys', 'persianvpnhub', 'filembad', 'moftconfig']
CHANNEL_ID = "VPNine1" 
CHANNEL_ID = "VPNine1" 
V2RAY_CHUNK_SIZE = 15    # حتماً روی ۱۵ بماند تا ارور لیمیت کاراکتر تلگرام ندهد
MTPROTO_CHUNK_SIZE = 10  
DELAY_BETWEEN_MSGS = 10

# تنظیمات مربوط به فیلتر پینگ (ایران)
ENABLE_PING_FILTER = True # True = فقط بدون پینگ‌ها | False = ارسال همه کانفیگ‌ها بدون تست
PING_TIMEOUT = 2.0       # حداکثر زمان انتظار برای پینگ (ثانیه)

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

def extract_ip_port(config):
    """استخراج IP و Port از انواع لینک‌ها برای گرفتن پینگ"""
    try:
        if config.startswith('vmess://'):
            b64_str = config[8:]
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            data = json.loads(base64.b64decode(b64_str).decode('utf-8'))
            return data.get('add'), int(data.get('port'))
        
        elif config.startswith(('vless://', 'trojan://', 'ss://', 'ssr://', 'tuic://', 'hysteria2://')):
            parsed = urllib.parse.urlparse(config)
            netloc = parsed.netloc
            if '@' in netloc:
                netloc = netloc.split('@')[1]
            if ':' in netloc:
                host, port = netloc.split(':')
                return host, int(port)
                
        elif config.startswith(('http', 'tg')): # MTProto
            parsed = urllib.parse.urlparse(config)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'server' in qs and 'port' in qs:
                return qs['server'][0], int(qs['port'][0])
    except Exception:
        pass
    return None, None

def check_ping(config):
    """تست اتصال (TCP Ping) به سرور"""
    host, port = extract_ip_port(config)
    if not host or not port:
        return False # اگر نتوانست استخراج کند، فرض می‌کنیم پینگ ندارد
        
    try:
        socket.setdefaulttimeout(PING_TIMEOUT)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, int(port)))
        s.close()
        return True # پینگ داد
    except Exception:
        return False # پینگ نداد (تایم‌اوت یا مسدود شده)

def filter_no_ping_configs(configs):
    """نگه داشتن کانفیگ‌هایی که پینگ *نمی‌دهند*"""
    selected = []
    print(f"Checking {len(configs)} configs for NO-PING rule...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(lambda c: (c, check_ping(c)), configs)
        for config, has_ping in results:
            if not has_ping: # فقط اگر پینگ نداد انتخاب می‌شود
                selected.append(config)
    return selected

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
    
    unique_v2ray = []
    unique_mtproto = []

    for link in new_v2ray:
        base = link.split('#')[0] if not link.startswith('vmess') else link
        if base not in history:
            unique_v2ray.append(link)
            history.add(base)
            
    for link in new_mtproto:
        if link not in history:
            unique_mtproto.append(link)
            history.add(link)

    # اجرای شرط فیلتر پینگ
    if ENABLE_PING_FILTER:
        print("Ping filter is ON. Filtering configs...")
        valid_v2ray = filter_no_ping_configs(unique_v2ray)
        valid_mtproto = filter_no_ping_configs(unique_mtproto)
    else:
        print("Ping filter is OFF. Processing all new configs...")
        valid_v2ray = unique_v2ray
        valid_mtproto = unique_mtproto

    total_sent = 0

    # ================= UI حرفه‌ای V2Ray =================
    for i in range(0, len(valid_v2ray), V2RAY_CHUNK_SIZE):
        chunk = valid_v2ray[i:i + V2RAY_CHUNK_SIZE]
        
        msg = "<blockquote expandable>"
        msg += "<code>"
        all_configs = ""
        for link in chunk:
            updated_link = update_remark(link, f"🚀@{CHANNEL_ID}")
            escaped_link = html.escape(updated_link)
            all_configs += f"{escaped_link}\n"
        
        msg += all_configs.strip()
        msg += "</code>\n"
        msg += "</blockquote>\n\n"
        
        # تغییر متن پیام بر اساس وضعیت فیلتر
        if ENABLE_PING_FILTER:
            msg += "<b>💎 V2Ray Servers (Filtered/No-Ping)</b>\n\n"
        else:
            msg += "<b>💎 V2Ray Servers (New Updates)</b>\n\n"
            
        msg += f"🛡 <b>Join:</b> @{CHANNEL_ID}\n"
        msg += "🌐 #v2ray #vless #vpn #config #کانفیگ\n"
        
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + V2RAY_CHUNK_SIZE < len(valid_v2ray) or valid_mtproto:
            print(f"Sent {len(chunk)} V2ray configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    # ================= UI حرفه‌ای پروکسی تلگرام =================
    for i in range(0, len(valid_mtproto), MTPROTO_CHUNK_SIZE):
        chunk = valid_mtproto[i:i + MTPROTO_CHUNK_SIZE]
        
        if ENABLE_PING_FILTER:
            msg = "<b>🛡 Premium MTProto Proxies (Filtered)</b>\n\n"
        else:
            msg = "<b>🛡 Premium MTProto Proxies (New Updates)</b>\n\n"
        
        for idx, link in enumerate(chunk, 1):
            escaped_link = html.escape(link)
            msg += f"🔹 <a href='{escaped_link}'>Connect to Proxy {idx}</a>\n"
            
        msg += f"\n\n🛡 <b>Join:</b> @{CHANNEL_ID}\n"
        msg += "🌐 #mtproto #proxy\n"

        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + MTPROTO_CHUNK_SIZE < len(valid_mtproto):
            print(f"Sent {len(chunk)} MTProto configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    save_history(history)
    print(f"Process finished. Successfully sent {total_sent} configs.")

if __name__ == '__main__':
    main()
