import os
import re
import json
import base64
import requests
import urllib.parse
import time
from bs4 import BeautifulSoup

# ================= تنظیمات =================
SOURCE_CHANNELS = ['v2rayng_org', 'v2ray_outline_ir'] # کانال‌های مبدا
CHANNEL_ID = "VPNine1" # اسم کانال شما برای نمایش در ریمارک (بدون @)
CHUNK_SIZE = 20 # تعداد در هر پیام

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
        f.write('\n'.join(list(history)[-2000:]))

def extract_host(config):
    """استخراج آی‌پی یا دامنه از کانفیگ برای پیدا کردن پرچم"""
    if config.startswith('vmess://'):
        try:
            b64_str = config[8:]
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            data = json.loads(base64.b64decode(b64_str).decode('utf-8'))
            return data.get('add') or data.get('host')
        except:
            return None
    else:
        # برای vless, trojan و ...
        match = re.search(r'://(?:[^@/]+@)?([^:/?#]+)', config)
        if match:
            return match.group(1)
    return None

def get_country_flag(host):
    """دریافت کد کشور از آی‌پی و تبدیل آن به ایموجی پرچم"""
    if not host: 
        return "🌍"
    try:
        # پاکسازی پورت از انتهای آی‌پی
        clean_host = host.split(':')[0]
        # استفاده از API رایگان برای یافتن لوکیشن
        resp = requests.get(f"http://ip-api.com/json/{clean_host}?fields=countryCode", timeout=5)
        if resp.status_code == 200:
            cc = resp.json().get('countryCode')
            if cc:
                # فرمول تبدیل کد 2 حرفی کشور به ایموجی پرچم
                return chr(ord(cc[0].upper()) + 127397) + chr(ord(cc[1].upper()) + 127397)
    except:
        pass
    return "🌍" # پرچم پیش‌فرض در صورت خطا

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
        if '#' in config:
            config = config.split('#')[0]
        config = config.rstrip(')')
        return f"{config}#{urllib.parse.quote(remark)}"

def fetch_configs():
    configs = set()
    pattern = r'(?:vless|vmess|trojan|ss|ssr|tuic|hysteria2?)://[^\s"\'<>\n]+'
    
    for channel in SOURCE_CHANNELS:
        try:
            url = f"https://t.me/s/{channel}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message_text')
                for msg in messages:
                    text = msg.get_text(separator=' ')
                    found = re.findall(pattern, text)
                    for c in found:
                        configs.add(c)
        except Exception as e:
            print(f"Error fetching from {channel}: {e}")
    return list(configs)

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
        print("Error: BOT_TOKEN or TARGET_CHANNEL is missing.")
        return

    history = load_history()
    new_configs = fetch_configs()
    valid_new_configs = []

    for config in new_configs:
        base_config = config.split('#')[0] if not config.startswith('vmess://') else config
        
        if base_config not in history:
            # ۱. استخراج آی‌پی/دامنه
            host = extract_host(config)
            
            # ۲. پیدا کردن پرچم
            flag = get_country_flag(host) if host else "🌍"
            if host:
                time.sleep(1.5) # تاخیر عمدی برای جلوگیری از بلاک شدن توسط سایت IP-API
                
            # ۳. ساخت ریمارک جدید (مثال: 🚀@VPNine1 - 🇩🇪)
            final_remark = f"🚀@{CHANNEL_ID} - {flag}"
            
            # ۴. اعمال در کانفیگ
            updated_config = update_remark(config, final_remark)
            valid_new_configs.append(updated_config)
            history.add(base_config)

for i in range(0, added_count, CHUNK_SIZE):
        chunk = valid_new_configs[i:i + CHUNK_SIZE]
        
        message_text = "<b>New Proxies Available ⚡️</b>\n"
        # اضافه کردن تگ باکس جمع‌شونده تلگرام
        message_text += "<blockquote expandable>"
        for c in chunk:
            message_text += f"<code>{c}</code>\n"
        message_text += "</blockquote>\n"
        
        message_text += f"🆔 @{CHANNEL_ID}"
        send_to_telegram(message_text)
    
    save_history(history)
    print(f"Process finished. {added_count} new configs forwarded.")

if __name__ == '__main__':
    main()
