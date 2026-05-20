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
import geoip2.database

# ================= تنظیمات =================
CHANNEL_ID = "VPNine1" 
V2RAY_CHUNK_SIZE = 10    
MTPROTO_CHUNK_SIZE = 10  
DELAY_BETWEEN_MSGS = 10

# تنظیمات کنترل ارسال
ENABLE_INTERNET_PRO = False   # True = پیدا کردن و ارسال کانفیگ‌های اینترنت پرو | False = خاموش
ENABLE_MTPROTO = False        
ENABLE_SH_X_IP = True        

# تنظیمات مربوط به فیلتر پینگ (ایران)
ENABLE_PING_FILTER = True 
PING_TIMEOUT = 2.0       

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TARGET_CHANNEL = os.environ.get('TARGET_CHANNEL')
# ===========================================

HISTORY_FILE = 'history.txt'
SOURCES_FILE = 'sources.txt'
SH_X_SOURCES_FILE = 'x.txt'

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return set(f.read().splitlines())
    return set()

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(list(history)[-8000:]))

def load_sources():
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
    sh_x_channels = []
    if not os.path.exists(SH_X_SOURCES_FILE):
        with open(SH_X_SOURCES_FILE, 'w', encoding='utf-8') as f:
            f.write("# لیست کانال‌های تلگرام برای بررسی اختصاصی آی‌پی ش.خ\n")
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

def get_country_info(ip_or_host):
    """آی‌پی را می‌گیرد و پرچم + مخفف کشور را به شکل پیوسته برمی‌گرداند"""
    db_path = 'GeoLite2-Country.mmdb'
    if not os.path.exists(db_path):
        return ""
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
        if not host: 
            return False
        
        if not re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', host):
            return False
            
        if config.startswith('vmess://'):
            b64_str = config[8:]
            b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
            data = json.loads(base64.b64decode(b64_str).decode('utf-8'))
            tls = data.get('tls', '').lower()
            if tls and tls != 'none':
                return False 
            return True
            
        elif config.startswith(('vless://', 'trojan://')):
            parsed = urllib.parse.urlparse(config)
            qs = urllib.parse.parse_qs(parsed.query)
            sec = qs.get('security', [''])[0].lower()
            if sec and sec != 'none':
                return False 
            return True
            
    except Exception:
        pass
    return False

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
    print(f"Checking {len(configs)} configs for NO-PING rule (Standard Net)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(lambda c: (c, check_ping(c)), configs)
        for config, has_ping in results:
            if not has_ping: 
                selected.append(config)
    return selected

def filter_pro_configs(configs):
    selected_pro = []
    print(f"Filtering {len(configs)} PRO configs for Datacenter and Active Ping...")
    
    valid_dcs = ['ovh', 'hetzner', 'digitalocean', 'linode', 'amazon', 'google', 'microsoft', 
                 'azure', 'oracle', 'leaseweb', 'contabo', 'vultr', 'aruba', 'akamai', 'cloudflare', 'fastly']
    
    asn_db_path = 'GeoLite2-ASN.mmdb'
    valid_asn_configs = []
    
    if os.path.exists(asn_db_path):
        try:
            with geoip2.database.Reader(asn_db_path) as reader:
                for config in configs:
                    host, port = extract_ip_port(config)
                    if not host: continue
                    
                    try:
                        response = reader.asn(host)
                        org = response.autonomous_system_organization.lower()
                        if any(dc in org for dc in valid_dcs):
                            valid_asn_configs.append(config)
                    except (geoip2.errors.AddressNotFoundError, Exception):
                        pass
        except Exception as e:
            print(f"ASN Database Error: {e}")
    else:
        print("ASN DB not found! Skipping datacenter check.")
        valid_asn_configs = configs

    print(f"Found {len(valid_asn_configs)} PRO configs with Valid Datacenters. Checking Ping...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(lambda c: (c, check_ping(c)), valid_asn_configs)
        for config, has_ping in results:
            if has_ping: 
                selected_pro.append(config)
                
    return selected_pro

def filter_iran_configs(configs):
    iran_configs = []
    print(f"Checking {len(configs)} V2Ray configs for IR location...")
    db_path = 'GeoLite2-Country.mmdb'
    
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found! Skipping GeoIP filter (returning empty).")
        return []

    try:
        with geoip2.database.Reader(db_path) as reader:
            for config in configs:
                host, port = extract_ip_port(config)
                if not host:
                    continue
                
                try:
                    if not re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', host):
                        ip = socket.gethostbyname(host)
                    else:
                        ip = host
                        
                    response = reader.country(ip)
                    if response.country.iso_code == 'IR':
                        iran_configs.append(config)
                except (geoip2.errors.AddressNotFoundError, socket.gaierror):
                    pass
    except Exception as e:
        print(f"GeoIP Database Error: {e}")
        
    print(f"Found {len(iran_configs)} IR configs out of {len(configs)}.")
    return iran_configs

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
    
    sh_x_posts_by_channel = {} 
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    union_channels = list(set(channels + sh_x_channels))

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
                    
                    if channel in channels:
                        for c in re.findall(pattern_v2ray, text): v2ray_links.add(c)
                        for c in re.findall(pattern_tg, text): mtproto_links.add(c)
                        
                        for a_tag in msg_text_div.find_all('a'):
                            href = a_tag.get('href')
                            if href:
                                for c in re.findall(pattern_v2ray, href): v2ray_links.add(c)
                                for c in re.findall(pattern_tg, href): mtproto_links.add(c)
                            
                    if ENABLE_SH_X_IP and (channel in sh_x_channels):
                        has_persian_keywords = 'شیر' in text and 'خورشید' in text
                        has_english_keywords = 'shir' in text_lower and 'khorshid' in text_lower
                        
                        ips = list(set(re.findall(pattern_ip, text)))
                        has_configs = bool(re.findall(pattern_v2ray, text)) or bool(re.findall(pattern_tg, text))
                        is_ip_list = len(ips) >= 4 and not has_configs
                        
                        if has_persian_keywords or has_english_keywords or is_ip_list:
                            if ips:
                                time_tag = widget.find('time')
                                dt_str = time_tag.get('datetime', '') if time_tag else ''
                                
                                if channel not in sh_x_posts_by_channel:
                                    sh_x_posts_by_channel[channel] = []
                                sh_x_posts_by_channel[channel].append((dt_str, ips))
                            
        except Exception as e:
            print(f"Error fetching channel {channel}: {e}")

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
            
    newest_sh_x_by_channel = {}
    for ch, posts in sh_x_posts_by_channel.items():
        posts.sort(key=lambda x: x[0])
        newest_sh_x_by_channel[ch] = posts[-1][1] 
            
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

    # ================= فیلتر تکراری‌های عمیق (Deep Deduplication) =================
    for link in new_v2ray:
        host, port = extract_ip_port(link)
        if host and port:
            # ساخت کلید اختصاصی بر اساس آی‌پی و پورت
            unique_key = f"{host}:{port}"
        else:
            # اگر دامین و پورت به درستی استخراج نشد، از کلینک خام به عنوان کلید استفاده می‌شود
            unique_key = link.split('#')[0] if not link.startswith('vmess') else link
            
        if unique_key not in history:
            unique_v2ray.append(link)
            history.add(unique_key)
            
    for link in new_mtproto:
        if link not in history:
            unique_mtproto.append(link)
            history.add(link)

    raw_pro_v2ray = []
    standard_v2ray = []
    
    for config in unique_v2ray:
        if ENABLE_INTERNET_PRO and is_internet_pro_config(config):
            raw_pro_v2ray.append(config)
        else:
            standard_v2ray.append(config)

    valid_pro_v2ray = filter_pro_configs(raw_pro_v2ray) if ENABLE_INTERNET_PRO else []
    valid_standard_v2ray = filter_iran_configs(standard_v2ray)

    if ENABLE_PING_FILTER:
        print("Ping filter is ON. Filtering standard configs...")
        valid_standard_v2ray = filter_no_ping_configs(valid_standard_v2ray)
        valid_mtproto = filter_no_ping_configs(unique_mtproto)
    else:
        print("Ping filter is OFF. Processing all new configs...")
        valid_mtproto = unique_mtproto

    total_sent = 0
    
    # ================= اصلاح منطق هش آی‌پی شیر و خورشید برای جلوگیری از تکرار =================
    if ENABLE_SH_X_IP and sh_x_ips_dict:
        for channel_name, ips in sh_x_ips_dict.items():
            # نام کانال حذف شد تا کلید بر اساس خود آی‌پی‌ها ساخته شود
            ip_hash = "SH_X_" + "_".join(sorted(ips))
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
            else:
                print(f"Skipped duplicate Sh_X IPs from channel: {channel_name}")

    # ================= ارسال کانفیگ‌های اینترنت پرو =================
    if ENABLE_INTERNET_PRO:
        for i in range(0, len(valid_pro_v2ray), V2RAY_CHUNK_SIZE):
            chunk = valid_pro_v2ray[i:i + V2RAY_CHUNK_SIZE]
            
            msg = "👨🏻‍💻 مخصوص اینترنت پرو\n\n"
            msg += "<blockquote expandable><code>\n"
            all_configs = ""
            for link in chunk:
                host, port = extract_ip_port(link)
                country_prefix = ""
                if host:
                    country_prefix = get_country_info(host)
                    
                updated_link = update_remark(link, f"{country_prefix}🚀@{CHANNEL_ID}")
                escaped_link = html.escape(updated_link)
                all_configs += f"{escaped_link}\n"
            
            msg += all_configs.strip()
            msg += "\n</code>\n"
            msg += "</blockquote>\n\n"
            msg += f"📡 @{CHANNEL_ID}\n"
            
            send_to_telegram(msg)
            total_sent += len(chunk)
            
            if i + V2RAY_CHUNK_SIZE < len(valid_pro_v2ray) or valid_standard_v2ray or (ENABLE_MTPROTO and valid_mtproto):
                print(f"Sent {len(chunk)} PRO V2ray configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
                time.sleep(DELAY_BETWEEN_MSGS)

    # ================= ارسال کانفیگ‌های معمولی (ایران) =================
    for i in range(0, len(valid_standard_v2ray), V2RAY_CHUNK_SIZE):
        chunk = valid_standard_v2ray[i:i + V2RAY_CHUNK_SIZE]
        
        msg = "<blockquote expandable>"
        msg += "<code>\n"
        all_configs = ""
        for link in chunk:
            host, port = extract_ip_port(link)
            country_prefix = ""
            if host:
                country_prefix = get_country_info(host)

            updated_link = update_remark(link, f"{country_prefix}🚀@{CHANNEL_ID}")
            escaped_link = html.escape(updated_link)
            all_configs += f"{escaped_link}\n"
        
        msg += all_configs.strip()
        msg += "\n</code>\n"
        msg += "</blockquote>\n\n"
        
        if ENABLE_PING_FILTER:
            msg += "<b>💎 بهینه شده برای نت ملی (ایران)</b>\n\n"
        else:
            msg += "<b>💎 V2Ray Servers (Iran)</b>\n\n"
            
        msg += f"🛡 <b>Join:</b> @{CHANNEL_ID}\n"
        msg += "🌐 #v2ray #vless #vpn #config #کانفیگ\n"
        
        send_to_telegram(msg)
        total_sent += len(chunk)
        
        if i + V2RAY_CHUNK_SIZE < len(valid_standard_v2ray) or (ENABLE_MTPROTO and valid_mtproto):
            print(f"Sent {len(chunk)} Standard V2ray configs. Waiting {DELAY_BETWEEN_MSGS} seconds...")
            time.sleep(DELAY_BETWEEN_MSGS)

    # ================= ارسال پروکسی‌های تلگرام =================
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
