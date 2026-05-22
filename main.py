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
import hashlib
from bs4 import BeautifulSoup
import geoip2.database
from datetime import datetime

# ================= تنظیمات =================
CHANNEL_ID = "VPNine1"
MAX_TELEGRAM_MSG_CHARS = 3800
MTPROTO_CHUNK_SIZE = 4
PSIPHON_CHUNK_SIZE = 4
DELAY_BETWEEN_MSGS = 10

# 🔴 حالت بی‌صدا (برای هماهنگ‌سازی دیتابیس بدون ارسال پیام)
SILENT_MODE = False  

# ================= کلیدهای مدیریت آپشن‌ها =================
ENABLE_INTERNET_PRO = False   
ENABLE_MTPROTO = True         
ENABLE_SH_X_IP = True         
ENABLE_PSIPHON = True         
ENABLE_PING_FILTER = True
PING_TIMEOUT = 2.0

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TARGET_CHANNEL = os.environ.get('TARGET_CHANNEL')

# === تنظیمات مربوط به اکانت دوم (گیت‌هاب) ===
GITHUB_TOKEN_DEST = os.environ.get('DEST_REPO_TOKEN')
DEST_REPO_OWNER = "vpnine1"
DEST_REPO_NAME = "sub"
# ===========================================

HISTORY_FILE = 'history.txt'
SOURCES_FILE = 'sources.txt'
SH_X_SOURCES_FILE = 'x.txt'
COUNTER_FILE = 'sub_counter.txt'

if SILENT_MODE:
    DELAY_BETWEEN_MSGS = 0

# ================= تابع فیلتر آی‌پی‌های مزاحم و DNS =================
def is_valid_public_ip(ip):
    dns_ips = {
        "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", 
        "149.112.112.112", "208.67.222.222", "208.67.220.220", 
        "4.2.2.1", "4.2.2.2", "4.2.2.3", "4.2.2.4", "4.2.2.5", "4.2.2.6", 
        "77.88.8.8", "77.88.8.1", "114.114.114.114", "8.26.56.26", 
        "8.20.247.20", "94.140.14.14", "94.140.15.15"
    }
    
    if ip in dns_ips:
        return False
        
    parts = ip.split('.')
    if len(parts) != 4: return False
    
    try:
        p1, p2 = int(parts[0]), int(parts[1])
        if p1 in [0, 10, 127] or p1 >= 224: return False 
        if p1 == 172 and 16 <= p2 <= 31: return False    
        if p1 == 192 and p2 == 168: return False         
    except:
        return False
        
    return True

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

def get_hash(text):
    text = text.strip()
    if '://' in text and not text.startswith('vmess://'):
        text = text.split('#')[0]
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def load_history():
    history = {}
    needs_conversion = False
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            for line in f.read().splitlines():
                line = line.strip()
                if not line: continue
                
                if len(line) == 32 and all(c in '0123456789abcdefABCDEF' for c in line):
                    history[line] = None
                else:
                    hashed = get_hash(line)
                    history[hashed] = None
                    needs_conversion = True
                    
    return history, needs_conversion

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(list(history.keys())[-8000:]))

def load_sub_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, 'r') as f:
            try:
                return int(f.read().strip())
            except Exception:
                return 1
    return 1

def save_sub_counter(count):
    with open(COUNTER_FILE, 'w') as f:
        f.write(str(count))

def upload_sub_to_github(filename, content_b64):
    if SILENT_MODE: return True 
        
    if not GITHUB_TOKEN_DEST:
        print("Error: DEST_REPO_TOKEN is missing!")
        return False
        
    url = f"https://api.github.com/repos/{DEST_REPO_OWNER}/{DEST_REPO_NAME}/contents/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN_DEST}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "message": f"Auto-add {filename} via API",
        "content": content_b64,
        "branch": "main" 
    }
    
    response = requests.put(url, headers=headers, json=data)
    
    if response.status_code == 201:
        print(f"✅ Successfully uploaded {filename} to GitHub.")
        return True
    elif response.status_code == 422:
        return True 
    else:
        return False

def load_file_lines(filepath, default_lines=[]):
    lines = []
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("# لطفاً آیدی کانال‌ها را اینجا قرار دهید\n")
            for d in default_lines: f.write(f"{d}\n")
            
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            if line.startswith('http://') or line.startswith('https://'):
                if 't.me/' in line:
                    ch = line.split('t.me/')[-1].split('/')[0].replace('s', '').replace('+', '')
                    if ch: lines.append(ch)
                else:
                    lines.append(line)
            elif line.startswith('@'):
                lines.append(line[1:])
            else:
                lines.append(line)
    return lines

def load_sources():
    raw_lines = load_file_lines(SOURCES_FILE, ["AR14N24B", "oneclickvpnkeys", "persianvpnhub", "filembad"])
    channels = [x for x in raw_lines if not x.startswith('http')]
    subs = [x for x in raw_lines if x.startswith('http')]
    return channels, subs

def load_sh_x_channels():
    return load_file_lines(SH_X_SOURCES_FILE, ["oneclickvpnkeys", "moftconfig"])

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

def get_country_info(ip_or_host):
    db_path = 'GeoLite2-Country.mmdb'
    if not os.path.exists(db_path): return ""
    try:
        if not re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', ip_or_host):
            ip = socket.gethostbyname(ip_or_host)
        else:
            ip = ip_or_host
            
        with geoip2.database.Reader(db_path) as reader:
            response = reader.country(ip)
            iso = response.country.iso_code
            if iso:
                flag = chr(ord(iso[0]) + 127397) + chr(ord(iso[1]) + 127397)
                return f"{flag}{iso}-"
    except Exception:
        pass
    return ""

def is_internet_pro_config(config):
    try:
        host, port = extract_ip_port(config)
        if not host or not re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', host): return False
            
        if config.startswith('vmess://'):
            b64_str = config[8:]
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            data = json.loads(base64.b64decode(b64_str).decode('utf-8'))
            tls = data.get('tls', '').lower()
            if tls and tls != 'none': return False 
            return True
            
        elif config.startswith(('vless://', 'trojan://')):
            parsed = urllib.parse.urlparse(config)
            qs = urllib.parse.parse_qs(parsed.query)
            sec = qs.get('security', [''])[0].lower()
            if sec and sec != 'none': return False 
            return True
    except Exception: pass
    return False

def check_ping(config):
    host, port = extract_ip_port(config)
    if not host or not port: return False
    try:
        socket.setdefaulttimeout(PING_TIMEOUT)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, int(port)))
        s.close()
        return True 
    except Exception: return False 

def filter_no_ping_configs(configs):
    selected = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        results = executor.map(lambda c: (c, check_ping(c)), configs)
        for config, has_ping in results:
            if not has_ping: selected.append(config)
    return selected

def filter_pro_configs(configs):
    selected_pro = []
    valid_dcs = ['ovh', 'hetzner', 'digitalocean', 'linode', 'amazon', 'google', 'microsoft', 
                 'azure', 'oracle', 'leaseweb', 'contabo', 'vultr', 'aruba', 'akamai', 'cloudflare', 'fastly']
    
    asn_db_path = 'GeoLite2-ASN.mmdb'
    reader = None
    if os.path.exists(asn_db_path):
        try: reader = geoip2.database.Reader(asn_db_path)
        except: pass

    def is_valid_pro(config):
        host, port = extract_ip_port(config)
        if not host: return False
        try:
            if not re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', host):
                ip = socket.gethostbyname(host)
            else: ip = host
                
            if reader:
                org = reader.asn(ip).autonomous_system_organization.lower()
                if not any(dc in org for dc in valid_dcs): return False
            
            socket.setdefaulttimeout(PING_TIMEOUT)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ip, int(port)))
            s.close()
            return True
        except: return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        results = executor.map(lambda c: (c, is_valid_pro(c)), configs)
        for config, is_valid in results:
            if is_valid: selected_pro.append(config)
                
    if reader: reader.close()
    return selected_pro

def filter_iran_configs(configs):
    iran_configs = []
    db_path = 'GeoLite2-Country.mmdb'
    if not os.path.exists(db_path): return []

    try: reader = geoip2.database.Reader(db_path)
    except: return []

    def check_is_iran(config):
        host, port = extract_ip_port(config)
        if not host: return False
        try:
            if not re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', host):
                ip = socket.gethostbyname(host)
            else: ip = host
            if reader.country(ip).country.iso_code == 'IR': return True
        except: pass
        return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        results = executor.map(lambda c: (c, check_is_iran(c)), configs)
        for config, is_ir in results:
            if is_ir: iran_configs.append(config)
                
    reader.close()
    return iran_configs

def decode_sub_text(text):
    try:
        clean_text = text.strip().replace('\n', '').replace('\r', '')
        clean_text += "=" * ((4 - len(clean_text) % 4) % 4)
        return base64.b64decode(clean_text).decode('utf-8')
    except: return text 

def fetch_raw_configs():
    channels, subs = load_sources()
    sh_x_channels = load_sh_x_channels() if ENABLE_SH_X_IP else []
    
    v2ray_links, mtproto_links = set(), set()
    psiphon_pairs = set()
    
    pattern_v2ray = r'(?:vless|vmess|trojan|ss|ssr|tuic|hysteria2?)://[^\s"\'<>\n]+'
    pattern_tg = r'(?:https?://t\.me/proxy\?[^\s"\'<>\n]+|tg://proxy\?[^\s"\'<>\n]+)'
    pattern_ip = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    
    # الگوی استخراج سایفون: آی‌پی و پورت حتماً باید در دو خط مجزا باشند
    pattern_psiphon_multiline = r'(?i)(?:ip|hostname|host)[\s:=-]*(\b(?:\d{1,3}\.){3}\d{1,3}\b)[^\n\r]*[\n\r]+[^\n\r]*?(?:port|پورت)[\s:=-]*(\d{2,5})'
    
    sh_x_all_ips = set() 
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    union_channels = list(set(channels + sh_x_channels))
    today_str = datetime.utcnow().strftime('%Y-%m-%d')

    for channel in union_channels:
        try:
            url = f"https://t.me/s/{channel}"
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message')
                
                for widget in messages:
                    msg_text_div = widget.find('div', class_='tgme_widget_message_text')
                    text = msg_text_div.get_text(separator='\n') if msg_text_div else ""
                    text_lower = text.lower()
                    
                    msg_is_today = False
                    time_tag = widget.find('time', class_='time')
                    if time_tag and time_tag.has_attr('datetime'):
                        if time_tag['datetime'].startswith(today_str):
                            msg_is_today = True
                    
                    if not msg_is_today:
                        continue
                    
                    # 1. سایفون
                    if ENABLE_PSIPHON:
                        is_psiphon = any(keyword in text_lower for keyword in ['psiphon', 'سایفون', 'سايفون'])
                        if is_psiphon:
                            matches = re.findall(pattern_psiphon_multiline, text)
                            for ip, port in matches:
                                if is_valid_public_ip(ip) and 1 <= int(port) <= 65535:
                                    psiphon_pairs.add((ip, port))
                            continue 

                    # 2. V2ray
                    if channel in channels:
                        for c in re.findall(pattern_v2ray, text): v2ray_links.add(c)
                        if msg_text_div:
                            for a_tag in msg_text_div.find_all('a'):
                                href = a_tag.get('href')
                                if href:
                                    for c in re.findall(pattern_v2ray, href): v2ray_links.add(c)
                                    
                    # 3. MTProto
                    for c in re.findall(pattern_tg, text): mtproto_links.add(c)
                    if msg_text_div:
                        for a_tag in msg_text_div.find_all('a'):
                            href = a_tag.get('href')
                            if href:
                                for c in re.findall(pattern_tg, href): mtproto_links.add(c)
                            
                    # 4. آی‌پی‌های ش.خ 
                    if ENABLE_SH_X_IP and (channel in sh_x_channels):
                        raw_ips = list(set(re.findall(pattern_ip, text)))
                        
                        valid_ips = [ip for ip in raw_ips if is_valid_public_ip(ip)]
                        
                        if len(valid_ips) >= 5:
                            for ip in valid_ips: sh_x_all_ips.add(ip)

        except Exception as e:
            print(f"Error fetching channel {channel}: {e}")

    for sub in subs:
        try:
            response = requests.get(sub, headers=headers, timeout=15)
            if response.status_code == 200:
                decoded_text = decode_sub_text(response.text)
                for c in re.findall(pattern_v2ray, decoded_text): v2ray_links.add(c)
                for c in re.findall(pattern_tg, decoded_text): mtproto_links.add(c)
        except Exception: pass
            
    return list(v2ray_links), list(mtproto_links), list(sh_x_all_ips), list(psiphon_pairs)
    

def send_to_telegram(text, reply_markup=None):
    if SILENT_MODE: return 
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TARGET_CHANNEL,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
        
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        print(f"Telegram API Error: {resp.text}")

def main():
    if not BOT_TOKEN or not TARGET_CHANNEL:
        print("Error: Missing credentials.")
        return

    history, needs_conversion = load_history()
    if needs_conversion:
        save_history(history)
        print("✅ History file converted and saved in standard MD5 Hash format.")

    sub_counter = load_sub_counter() 
    
    print("⏳ در حال جمع‌آوری اطلاعات از کانال‌ها...")
    new_v2ray, new_mtproto, sh_x_all_ips, psiphon_pairs = fetch_raw_configs()

    print("\n================ گزارش جستجوی خام ================")
    print(f"🔍 مجموع V2Ray پیدا شده: {len(new_v2ray)}")
    print(f"🔍 مجموع MTProto پیدا شده: {len(new_mtproto)}")
    print(f"🔍 مجموع آی‌پی‌های ش.خ: {len(sh_x_all_ips)}")
    print(f"🔍 مجموع سرورهای سایفون (امروز): {len(psiphon_pairs)}")
    print("==================================================\n")

    if ENABLE_PSIPHON and psiphon_pairs:
        unique_psiphon = []
        for ip, port in psiphon_pairs:
            ph_hash = get_hash(f"PSIPHON_{ip}_{port}")
            if ph_hash not in history:
                unique_psiphon.append((ip, port))
                history[ph_hash] = None
        
        if unique_psiphon:
            print(f"✅ {len(unique_psiphon)} کانفیگ جدید سایفون برای ارسال آماده شد.")
            chunk_size = PSIPHON_CHUNK_SIZE
            for i in range(0, len(unique_psiphon), chunk_size):
                chunk = unique_psiphon[i:i + chunk_size]
                msg = "<b>✨ Psiphon Hosts & Ports</b>\n\n"
                for ip, port in chunk:
                    msg += f"Host: <code>{ip}</code>\nPort: <code>{port}</code>\n\n"
                msg += f"📡 @{CHANNEL_ID}"
                send_to_telegram(msg)
                print(f"📤 Sent {len(chunk)} Psiphon configs to Telegram.")
                time.sleep(DELAY_BETWEEN_MSGS)

    unique_v2ray, unique_mtproto = [], []
    for link in new_v2ray:
        link_hash = get_hash(link)
        if link_hash not in history:
            unique_v2ray.append(link)
            history[link_hash] = None
            
    for link in new_mtproto:
        link_hash = get_hash(link)
        if link_hash not in history:
            unique_mtproto.append(link)
            history[link_hash] = None

    print(f"✅ پس از بررسی تاریخچه: {len(unique_v2ray)} V2Ray و {len(unique_mtproto)} MTProto کاملاً جدید هستند.")

    raw_pro_v2ray, standard_v2ray = [], []
    for config in unique_v2ray:
        if ENABLE_INTERNET_PRO and is_internet_pro_config(config):
            raw_pro_v2ray.append(config)
        else:
            standard_v2ray.append(config)

    valid_pro_v2ray = filter_pro_configs(raw_pro_v2ray) if ENABLE_INTERNET_PRO else []
    valid_standard_v2ray = filter_iran_configs(standard_v2ray)

    if ENABLE_PING_FILTER:
        print("⏳ در حال پینگ گرفتن و تست سرورها...")
        valid_standard_v2ray = filter_no_ping_configs(valid_standard_v2ray)
        valid_mtproto = filter_no_ping_configs(unique_mtproto)
    else:
        valid_mtproto = unique_mtproto

    total_sent = 0
    
    if ENABLE_SH_X_IP and sh_x_all_ips:
        new_sh_x = []
        for ip in set(sh_x_all_ips):
            ip_hash = get_hash(f"SHX_{ip}")
            if ip_hash not in history:
                new_sh_x.append(ip)
                history[ip_hash] = None
        
        if new_sh_x:
            new_sh_x.sort()
            print(f"✅ {len(new_sh_x)} آی‌پی جدید ش.خ برای ارسال آماده شد.")
            chunk_size = 150 
            for i in range(0, len(new_sh_x), chunk_size):
                chunk = new_sh_x[i:i + chunk_size]
                msg = "<b>آی پی برنامه 🦁☀️</b>\n\n<blockquote expandable><code>\n"
                msg += "\n".join(chunk)
                msg += "\n</code></blockquote>\n\n"
                msg += f"⚙️ @{CHANNEL_ID}"

                send_to_telegram(msg, reply_markup=reply_markup)
                print(f"📤 Sent {len(chunk)} New Sh_X IPs to Telegram.")
                time.sleep(DELAY_BETWEEN_MSGS)

    if ENABLE_INTERNET_PRO and valid_pro_v2ray:
        chunk, chunk_sub_links, current_char_count = [], [], 0
        base_msg = f"👨🏻‍💻 مخصوص اینترنت پرو\n\n<blockquote expandable><code>\n</code>\n</blockquote>\n\n📡 @{CHANNEL_ID}\n"
        max_allowed_chars = MAX_TELEGRAM_MSG_CHARS - len(base_msg)
        
        def send_pro_batch(batch, sub_links):
            nonlocal sub_counter, total_sent
            msg = "👨🏻‍💻 مخصوص اینترنت پرو\n\n<blockquote expandable><code>\n"
            msg += "\n".join(batch) + "\n</code>\n</blockquote>\n\n" + f"📡 @{CHANNEL_ID}\n"
            
            sub_filename = f"@VPNine1-sub{sub_counter}"
            sub_url = f"https://raw.githubusercontent.com/vpnine1/sub/main/{sub_filename}#{sub_filename}"
            sub_content = '\n'.join(sub_links)
            sub_b64 = base64.b64encode(sub_content.encode('utf-8')).decode('utf-8')
            
            reply_markup = {"inline_keyboard": [[{"text": "🔗 کپی لینک ساب کانفیگ", "copy_text": {"text": sub_url}}]]}
            
            if upload_sub_to_github(sub_filename, sub_b64):
                send_to_telegram(msg, reply_markup=reply_markup)
                if not SILENT_MODE: sub_counter += 1
            else:
                send_to_telegram(msg, reply_markup=None)
            total_sent += len(batch)
            print(f"📤 Sent {len(batch)} Pro V2Ray configs to Telegram.")
            time.sleep(DELAY_BETWEEN_MSGS)

        for link in valid_pro_v2ray:
            host, _ = extract_ip_port(link)
            country_prefix = get_country_info(host) if host else ""
            updated_link = update_remark(link, f"{country_prefix}🚀@{CHANNEL_ID}")
            escaped_link, line_len = html.escape(updated_link), len(html.escape(updated_link)) + 1 
            
            if current_char_count + line_len > max_allowed_chars and chunk:
                send_pro_batch(chunk, chunk_sub_links)
                chunk, chunk_sub_links, current_char_count = [], [], 0
            
            chunk.append(escaped_link); chunk_sub_links.append(updated_link); current_char_count += line_len
            
        if chunk: send_pro_batch(chunk, chunk_sub_links)

    if valid_standard_v2ray:
        chunk, chunk_sub_links, current_char_count = [], [], 0
        bottom_text = "<b>⚙️ اختصاصی برای اینترنت ملی</b>\n\n" if ENABLE_PING_FILTER else "<b>💎 V2Ray Servers (Iran)</b>\n\n"
        bottom_text += f"✅ <b>Join:</b> @{CHANNEL_ID}\n🌐 #v2ray #vless #vpn #config #کانفیگ\n"
        base_msg = f"<blockquote expandable><code>\n</code>\n</blockquote>\n\n{bottom_text}"
        max_allowed_chars = MAX_TELEGRAM_MSG_CHARS - len(base_msg)
        
        def send_std_batch(batch, sub_links):
            nonlocal sub_counter, total_sent
            msg = "<blockquote expandable><code>\n" + "\n".join(batch) + "\n</code>\n</blockquote>\n\n" + bottom_text
            
            sub_filename = f"@VPNine1-sub{sub_counter}"
            sub_url = f"https://raw.githubusercontent.com/vpnine1/sub/main/{sub_filename}#{sub_filename}"
            sub_content = '\n'.join(sub_links)
            sub_b64 = base64.b64encode(sub_content.encode('utf-8')).decode('utf-8')
            
            reply_markup = {"inline_keyboard": [[{"text": "🔗 کپی لینک ساب کانفیگ", "copy_text": {"text": sub_url}}]]}
            
            if upload_sub_to_github(sub_filename, sub_b64):
                send_to_telegram(msg, reply_markup=reply_markup)
                if not SILENT_MODE: sub_counter += 1
            else:
                send_to_telegram(msg, reply_markup=None)
            total_sent += len(batch)
            print(f"📤 Sent {len(batch)} Standard V2Ray configs to Telegram.")
            time.sleep(DELAY_BETWEEN_MSGS)

        for link in valid_standard_v2ray:
            host, _ = extract_ip_port(link)
            country_prefix = get_country_info(host) if host else ""
            updated_link = update_remark(link, f"{country_prefix}🚀@{CHANNEL_ID}")
            escaped_link, line_len = html.escape(updated_link), len(html.escape(updated_link)) + 1 
            
            if current_char_count + line_len > max_allowed_chars and chunk:
                send_std_batch(chunk, chunk_sub_links)
                chunk, chunk_sub_links, current_char_count = [], [], 0
            
            chunk.append(escaped_link); chunk_sub_links.append(updated_link); current_char_count += line_len
            
        if chunk: send_std_batch(chunk, chunk_sub_links)

    if ENABLE_MTPROTO and valid_mtproto:
        for i in range(0, len(valid_mtproto), MTPROTO_CHUNK_SIZE):
            chunk = valid_mtproto[i:i + MTPROTO_CHUNK_SIZE]
            msg = "<b>🟢 Premium MTProto Proxies (نت ملی)</b>\n\n" if ENABLE_PING_FILTER else "<b>🛡 Premium MTProto Proxies</b>\n\n"
            msg += f"✅ @{CHANNEL_ID}\n🌐 #mtproto #proxy\n"
            
            inline_keyboard = []
            row = []
            for idx, link in enumerate(chunk, 1):
                row.append({"text": f"Connect", "url": link})
                if len(row) == 2: 
                    inline_keyboard.append(row)
                    row = []
            if row: inline_keyboard.append(row)
            
            reply_markup = {"inline_keyboard": inline_keyboard}
            send_to_telegram(msg, reply_markup=reply_markup)
            total_sent += len(chunk)
            print(f"📤 Sent {len(chunk)} MTProto proxies to Telegram.")
            time.sleep(DELAY_BETWEEN_MSGS)
    
    if not SILENT_MODE: save_sub_counter(sub_counter)
    save_history(history)
    
    if SILENT_MODE:
        print(f"\n✅ SILENT MODE FINISHED. Processed {total_sent} items. History is updated. NOW SET 'SILENT_MODE = False' AND RUN AGAIN.")
    else:
        print(f"\n🏁 Process finished! Total new items sent to Telegram: {total_sent}")

if __name__ == '__main__':
    main()
