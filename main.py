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
CHANNEL_ID = "VPNine1" 
V2RAY_CHUNK_SIZE = 10    # حتماً روی ۱۵ بماند تا ارور لیمیت کاراکتر تلگرام ندهد
MTPROTO_CHUNK_SIZE = 10  
DELAY_BETWEEN_MSGS = 10

# تنظیمات کنترل ارسال
ENABLE_MTPROTO = False        # True = پروکسی‌های تلگرام ارسال شوند | False = متوقف کردن ارسال پروکسی تلگرام
ENABLE_SH_X_IP = True        # True = پیدا کردن و ارسال آی‌پی‌های ش.خ | False = خاموش

# تنظیمات مربوط به فیلتر پینگ (ایران)
ENABLE_PING_FILTER = True # True = فقط بدون پینگ‌ها | False = ارسال همه کانفیگ‌ها بدون تست
PING_TIMEOUT = 2.0       # حداکثر زمان انتظار برای پینگ (ثانیه)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TARGET_CHANNEL = os.environ.get('TARGET_CHANNEL')
# ===========================================

HISTORY_FILE = 'history.txt'
SOURCES_FILE = 'sources.txt'
SH_X_SOURCES_FILE = 'x.txt' # فایل حاوی منابع اختصاصی آی‌پی ش.خ

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return set(f.read().splitlines())
    return set()

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(list(history)[-8000:]))

def load_sources():
    """خواندن منابع عمومی از فایل متنی و تفکیک کانال‌ها و لینک‌های ساب"""
    channels = []
    subs = []
    
    if not os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            f.write("# لینک‌های ساب و آیدی کانال‌ها را اینجا قرار دهید\n")
            f.write("AR14N24B\n")
            f.write("oneclickvpnkeys\n")
            f.write("persianvpnhub\n")
            f.write("filembad\n")
            f.write("moftconfig\n")
            f.write("v2ray_configs_pool\n")
            f.write("# https://example.com/sub_link\n")
    
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if line.startswith('http://') or line.startswith('https://'):
                if 't.me/' in line:
                    ch = line.split('t.me/')[-1].split('/')[0].replace('s', '').replace('+', '')
                    if ch: channels.append(ch)
                else:
                    subs.append(line)
            elif line.startswith('@'):
                channels.append(line[1:])
            else:
                channels.append(line)
                
    return channels, subs

def load_sh_x_channels():
    """خواندن کانال‌های اختصاصی جهت بررسی آی‌پی ش.خ از فایل x.txt"""
    sh_x_channels = []
    if not os.path.exists(SH_X_SOURCES_FILE):
        with open(SH_X_SOURCES_FILE, 'w', encoding='utf-8') as f:
            f.write("# لیست کانال‌های تلگرام برای بررسی اختصاصی آی‌پی ش.خ را اینجا وارد کنید (هر خط یک آیدی)\n")
            f.write("oneclickvpnkeys\n")
            f.write("moftconfig\n")
            
    with open(SH_X_SOURCES_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('@'):
                sh_x_channels.append(line[1:])
            elif 't.me/' in line:
                ch = line.split('t.me/')[-1].split('/')[0].replace('s', '').replace('+', '')
                if ch: sh_x_channels.append(ch)
            else:
                sh_x_channels.append(line)
    return sh_x_channels

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
                
        elif config.startswith(('http', 'tg')):
            parsed = urllib.parse.urlparse(config)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'server' in qs and 'port' in qs:
                return qs['server'][0], int(qs['port'][0])
    except Exception:
        pass
    return None, None

def check_ping(config):
    host, port = extract_ip_port(config)
    if not host or not port:
        return False
        
    try:
        socket.setdefaulttimeout(PING_TIMEOUT)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, int(port)))
        s.close()
        return True 
    except Exception:
        return False 

def filter_no_ping_configs(configs):
    selected = []
    print(f"Checking {len(configs)} configs for NO-PING rule...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(lambda c: (c, check_ping(c)), configs)
        for config, has_ping in results:
            if not has_ping: 
                selected.append(config)
    return selected

def decode_sub_text(text):
    try:
        clean_text = text.strip().replace('\n', '').replace('\r', '')
        clean_text += "=" * ((4 - len(clean_text) % 4) % 4)
        decoded = base64.b64decode(clean_text).decode('utf-8')
        return decoded
    except Exception:
        return text 

def fetch_raw_configs():
    channels, subs = load_sources()
    sh_x_channels = load_sh_x_channels()
    
    print(f"Loaded {len(channels)} general channels, {len(sh_x_channels)} sh_x channels, and {len(subs)} sub links.")
    
    v2ray_links, mtproto_links = set(), set()
    pattern_v2ray = r'(?:vless|vmess|trojan|ss|ssr|tuic|hysteria2?)://[^\s"\'<>\n]+'
    pattern_tg = r'(?:https?://t\.me/proxy\?[^\s"\'<>\n]+|tg://proxy\?[^\s"\'<>\n]+)'
    pattern_ip = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    
    sh_x_posts_by_channel = {} # ذخیره تفکیک‌شده پست‌های هر کانال ش.خ
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    union_channels = list(set(channels + sh_x_channels))

    # 1. پردازش کانال‌های تلگرام
    for channel in union_channels:
        try:
            url = f"https://t.me/s/{channel}"
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message')
                
                for widget in messages:
                    msg_text_div = widget.find('div', class_='tgme_widget_message_text')
                    if not msg_text_div: continue
                    
                    text = msg_text_div.get_text(separator=' ')
                    text_lower = text.lower()
                    
                    # استخراج کانفیگ‌های معمولی (اگر کانال جزو لیست عمومی sources.txt باشد)
                    if channel in channels:
                        for c in re.findall(pattern_v2ray, text): v2ray_links.add(c)
                        for c in re.findall(pattern_tg, text): mtproto_links.add(c)
                        
                        for a_tag in msg_text_div.find_all('a'):
                            href = a_tag.get('href')
                            if href:
                                for c in re.findall(pattern_v2ray, href): v2ray_links.add(c)
                                for c in re.findall(pattern_tg, href): mtproto_links.add(c)
                            
                    # استخراج پست‌های مربوط به ش.خ (فقط در صورتی که کانال در لیست x.txt باشد)
                    if ENABLE_SH_X_IP and (channel in sh_x_channels):
                        has_persian_keywords = 'شیر' in text and 'خورشید' in text
                        has_english_keywords = 'shir' in text_lower and 'khorshid' in text_lower
                        
                        # بررسی وجود لیست آی‌پی (حداقل ۴ آی‌پی یکتا) و عدم وجود پروتکل‌های V2ray/Proxy برای جلوگیری از اشتباه
                        ips = list(set(re.findall(pattern_ip, text)))
                        has_configs = bool(re.findall(pattern_v2ray, text)) or bool(re.findall(pattern_tg, text))
                        is_ip_list = len(ips) >= 4 and not has_configs
                        
                        if has_persian_keywords or has_english_keywords or is_ip_list:
                            if ips:
                                # استخراج زمان پست برای پیدا کردن جدیدترین
                                time_tag = widget.find('time')
                                dt_str = time_tag.get('datetime', '') if time_tag else ''
                                
                                if channel not in sh_x_posts_by_channel:
                                    sh_x_posts_by_channel[channel] = []
                                sh_x_posts_by_channel[channel].append((dt_str, ips))
                            
        except Exception as e:
            print(f"Error fetching channel {channel}: {e}")

    # 2. پردازش لینک‌های ساب عمومی
    for sub in subs:
        try:
            response = requests.get(sub, headers=headers, timeout=15)
            if response.status_code == 200:
                raw_text = response.text
                decoded_text = decode_sub_text(raw_text)
                
                for c in re.findall(pattern_v2ray, decoded_text): v2ray_links.add(c)
                for c in re.findall(pattern_tg, decoded_text): mtproto_links.add(c)
        except Exception as e:
            print(f"Error fetching sub link {sub}: {e}")
            
    # پیدا کردن جدیدترین آی‌پی‌های ش.خ به تفکیک «هر کانال» به صورت جداگانه
    newest_sh_x_by_channel = {}
    for ch, posts in sh_x_posts_by_channel.items():
        # سورت کردن پست‌های همان کانال بر اساس تاریخ
        posts.sort(key=lambda x: x[0])
        newest_sh_x_by_channel[ch] = posts[-1][1] # ذخیره آخرین (جدیدترین) پست این کانال
            
    return list(v2ray_links), list(mtproto_links), newest_sh_x_by_channel

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
    new_v2ray, new_mtproto, sh_x_ips_dict = fetch_raw_configs()
    
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

    if ENABLE_PING_FILTER:
        print("Ping filter is ON. Filtering configs...")
        valid_v2ray = filter_no_ping_configs(unique_v2ray)
        valid_mtproto = filter_no_ping_configs(unique_mtproto)
    else:
        print("Ping filter is OFF. Processing all new configs...")
        valid_v2ray = unique_v2ray
        valid_mtproto = unique_mtproto

    total_sent = 0
    
    # ================= ارسال آی‌پی‌های ش.خ به تفکیک هر کانال در پست مجزا =================
    if ENABLE_SH_X_IP and sh_x_ips_dict:
        for channel_name, ips in sh_x_ips_dict.items():
            # ایجاد یک هش اختصاصی متصل به آیدی همان کانال برای کنترل تکراری‌ها
            ip_hash = f"SH_X_{channel_name}_" + "_".join(sorted(ips))
            if ip_hash not in history:
                msg = "آی پی برنامه 🦁☀️\n\n"
                msg += "<blockquote expandable><code>\n"
                for ip in ips:
                    msg += f"{ip}\n"
                msg += "</code></blockquote>\n\n"
                msg += f"⚙️ @{CHANNEL_ID}"
                
                send_to_telegram(msg)
                history.add(ip_hash)
                print(f"Sent {len(ips)} Sh_X IPs from channel: {channel_name}")
                time.sleep(DELAY_BETWEEN_MSGS)

    # ================= UI حرفه‌ای V2Ray =================
    for i in range(0, len(valid_v2ray), V2RAY_CHUNK_SIZE):
        chunk = valid_v2ray[i:i + V2RAY_CHUNK_SIZE]
        
        msg = "<blockquote expandable>"
        msg += "<code>\n"
        all_configs = ""
        for link in chunk:
            updated_link = update_remark(link, f"🚀@{CHANNEL_ID}")
            escaped_link = html.escape(updated_link)
            all_configs += f"{escaped_link}\n"
        
        msg += all_configs.strip()
        msg += "\n</code>\n"
        msg += "</blockquote>\n\n"
        
        if ENABLE_PING_FILTER:
            msg += "<b>💎 بهینه شده برای نت ملی</b>\n\n"
        else:
            msg += "<b>💎 V2Ray Servers (New Updates)</b>\n\n"
            
        msg += f"🛡 <b>Join:</b> @{CHANNEL_ID}\n"
        msg += "🌐 #v2ray #vless #vpn #config #کانفیگ\n"
        
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + V2RAY_CHUNK_SIZE < len(valid_v2ray) or (ENABLE_MTPROTO and valid_mtproto):
            print(f"Sent {len(chunk)} V2ray configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    # ================= UI حرفه‌ای پروکسی تلگرام =================
    if ENABLE_MTPROTO:
        for i in range(0, len(valid_mtproto), MTPROTO_CHUNK_SIZE):
            chunk = valid_mtproto[i:i + MTPROTO_CHUNK_SIZE]
            
            if ENABLE_PING_FILTER:
                msg = "<b>🛡 Premium MTProto Proxies (نت ملی)</b>\n\n"
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
    print(f"Process finished. Successfully sent {total_sent} standard configs.")

if __name__ == '__main__':
    main()
