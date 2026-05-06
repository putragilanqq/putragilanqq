#!/usr/bin/env python3
"""
WPScan API Token Extractor
Login ke wpscan.com dan otomatis extract API token, simpan ke api_result.txt
"""

import requests
import json
import time
import random
import os
import re
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

# User Agents untuk rotating
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
]

class WPScanChecker:
    def __init__(self):
        self.session = self._create_session()
        self.base_url = "https://wpscan.com"
        self.csrf_token = None
        self.current_user_agent = None
        
    def _get_random_user_agent(self):
        """Get random user agent"""
        return random.choice(USER_AGENTS)
    
    def _create_session(self):
        """Create session dengan retry strategy"""
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
    
    def get_csrf_token(self):
        """Extract CSRF token dari sign-in page"""
        try:
            print("[→] Fetching sign-in page...")
            response = self.session.get(f"{self.base_url}/sign-in", timeout=10)
            print(f"[*] Status Code: {response.status_code}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Cari CSRF token dari berbagai sources
            # Method 1: Meta tag
            csrf_meta = soup.find('meta', {'name': 'csrf-token'})
            if csrf_meta:
                self.csrf_token = csrf_meta.get('content')
                print("[✓] CSRF token dari meta tag")
                return self.csrf_token
            
            # Method 2: Input hidden
            csrf_input = soup.find('input', {'name': '_token'})
            if csrf_input:
                self.csrf_token = csrf_input.get('value')
                print("[✓] CSRF token dari form input")
                return self.csrf_token
            
            # Method 3: Cari di JavaScript
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'csrf' in script.string.lower():
                    match = re.search(r'["\']csrf["\']?\s*:\s*["\']([a-zA-Z0-9/+=\-_.]+)["\']', script.string)
                    if match:
                        self.csrf_token = match.group(1)
                        print("[✓] CSRF token dari JavaScript")
                        return self.csrf_token
            
            print("[!] CSRF token tidak ditemukan")
            return None
            
        except Exception as e:
            print(f"[✗] Error getting CSRF token: {e}")
            return None
    
    def login(self, email, password, remember_me=False):
        """Login ke WPScan"""
        try:
            # Get CSRF token first
            if not self.get_csrf_token():
                print("[!] Melanjutkan login tanpa CSRF token...")
            
            # Prepare payload sesuai format yang diminta
            payload = {
                "email": email,
                "password": password,
                "remember_me": remember_me
            }
            
            print(f"\n[→] Attempting login ke WPScan...")
            print(f"[*] Email: {email}")
            print(f"[*] Remember me: {remember_me}")
            
            if self.csrf_token:
                payload["_token"] = self.csrf_token
            
            # Try JSON POST first
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            if self.csrf_token:
                headers["X-CSRF-TOKEN"] = self.csrf_token
            
            print("[→] Sending JSON login request...")
            response = self.session.post(
                f"{self.base_url}/sign-in",
                json=payload,
                headers=headers,
                allow_redirects=True,
                timeout=15
            )
            
            print(f"[*] Status Code: {response.status_code}")
            print(f"[*] URL after redirect: {response.url}")
            
            # Check if login successful
            if response.status_code == 200:
                if "profile" in response.url or "dashboard" in response.url:
                    print("[✓] Login berhasil!")
                    return True
                elif "sign-in" not in response.url:
                    print("[✓] Login berhasil!")
                    return True
            
            # Try form-encoded POST
            print("\n[→] Trying form-encoded login...")
            form_payload = {
                "email": email,
                "password": password,
                "remember_me": "on" if remember_me else None
            }
            
            if self.csrf_token:
                form_payload["_token"] = self.csrf_token
            
            form_payload = {k: v for k, v in form_payload.items() if v is not None}
            
            response2 = self.session.post(
                f"{self.base_url}/sign-in",
                data=form_payload,
                allow_redirects=True,
                timeout=15
            )
            
            print(f"[*] Status Code: {response2.status_code}")
            print(f"[*] URL after redirect: {response2.url}")
            
            if response2.status_code == 200:
                if "profile" in response2.url or "dashboard" in response2.url:
                    print("[✓] Login berhasil (form-encoded)!")
                    return True
                elif "sign-in" not in response2.url:
                    print("[✓] Login berhasil (form-encoded)!")
                    return True
            
            print("[✗] Login gagal")
            return False
                
        except Exception as e:
            print(f"[✗] Error during login: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def extract_api_token(self):
        """Extract API token dari profile page"""
        try:
            print("\n[→] Fetching profile page...")
            response = self.session.get(f"{self.base_url}/profile", timeout=15)
            print(f"[*] Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"[✗] Failed to access profile: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Debug: Print page title
            title = soup.find('title')
            print(f"[*] Page Title: {title.get_text() if title else 'No title'}")
            
            api_token = None
            
            # Method 1: Cari di element dengan text "API Token"
            print("[→] Method 1: Looking for API Token label...")
            for elem in soup.find_all(['div', 'section', 'p']):
                text = elem.get_text()
                if 'API Token' in text or 'api token' in text.lower():
                    print(f"[*] Found API Token section")
                    
                    # Cari input atau span dengan token value
                    # Biasanya format: <input value="token"> atau <span>token</span>
                    input_elem = elem.find('input', {'type': 'text'})
                    if input_elem:
                        api_token = input_elem.get('value')
                        print(f"[✓] Found token in input field")
                        break
                    
                    span_elem = elem.find('span')
                    if span_elem:
                        token_text = span_elem.get_text(strip=True)
                        if len(token_text) > 30:  # API tokens usually long
                            api_token = token_text
                            print(f"[✓] Found token in span")
                            break
            
            # Method 2: Regex search untuk pattern token
            if not api_token:
                print("[→] Method 2: Using regex pattern...")
                page_text = soup.get_text()
                
                # Look for common token patterns (alphanumeric, long string)
                matches = re.findall(r'[A-Za-z0-9]{30,}', page_text)
                
                if matches:
                    # Filter likely tokens (exclude common words)
                    for match in matches:
                        if not any(x in match.lower() for x in ['hello', 'hello,', 'naeem']):
                            api_token = match
                            print(f"[✓] Found potential token via regex")
                            break
            
            # Method 3: Cari di HTML attributes
            if not api_token:
                print("[→] Method 3: Searching HTML attributes...")
                for elem in soup.find_all(['input', 'span', 'div']):
                    # Check all attributes
                    for attr, value in elem.attrs.items():
                        if isinstance(value, str) and len(value) > 30:
                            # Check if looks like a token
                            if re.match(r'^[A-Za-z0-9_\-+=/.]{30,}$', value):
                                if not any(x in value.lower() for x in ['http', 'www', '.com']):
                                    api_token = value
                                    print(f"[✓] Found token in attribute: {attr}")
                                    break
                    if api_token:
                        break
            
            # Method 4: Search untuk specific ID patterns
            if not api_token:
                print("[→] Method 4: Looking for specific patterns...")
                
                # Cari elemen dengan ID atau class yang mengandung 'token'
                token_elements = soup.find_all(id=re.compile('token', re.I))
                token_elements.extend(soup.find_all(class_=re.compile('token', re.I)))
                
                for elem in token_elements:
                    if elem.name == 'input':
                        api_token = elem.get('value')
                        if api_token:
                            print(f"[✓] Found token from element ID/class")
                            break
                    elif elem.name in ['span', 'div']:
                        text = elem.get_text(strip=True)
                        if len(text) > 30 and not any(x in text.lower() for x in ['api', 'token', 'label']):
                            api_token = text
                            print(f"[✓] Found token from element ID/class")
                            break
            
            if api_token:
                print(f"\n[✓] API Token extracted successfully!")
                print(f"[*] Token: {api_token[:20]}...{api_token[-10:]}")
                return api_token
            else:
                print("[✗] API Token not found on profile page")
                # Debug: Print relevant page sections
                print("[DEBUG] Searching page for token-like strings...")
                all_text = soup.get_text()
                # Find sections with "API" or token-like content
                for line in all_text.split('\n'):
                    if 'API' in line or (len(line) > 30 and line.count(line[0]) < len(line) * 0.5):
                        print(f"[DEBUG] {line[:100]}")
                return None
            
        except Exception as e:
            print(f"[✗] Error extracting API token: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_token(self, email, api_token, output_file="api_result.txt"):
        """Save API token ke file"""
        try:
            result_data = {
                "email": email,
                "api_token": api_token,
                "timestamp": datetime.now().isoformat()
            }
            
            with open(output_file, 'a') as f:
                f.write(json.dumps(result_data) + '\n')
            
            print(f"\n[💾] API Token saved to {output_file}")
            print(f"[✓] Email: {email}")
            print(f"[✓] Token: {api_token[:20]}...{api_token[-10:]}")
            return True
        
        except Exception as e:
            print(f"[✗] Error saving token: {e}")
            return False
    
    def check_account(self, email, password, remember_me=False):
        """Main: login dan extract API token"""
        print("\n" + "=" * 70)
        print("WPScan API Token Extractor")
        print("=" * 70)
        print(f"Email: {email}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Login
        if not self.login(email, password, remember_me):
            return {"status": "failed", "message": "Login gagal"}
        
        time.sleep(2)  # Wait for page load
        
        # Extract API token
        api_token = self.extract_api_token()
        
        if api_token:
            # Save to file
            self.save_token(email, api_token)
            
            return {
                "status": "success",
                "email": email,
                "api_token": api_token
            }
        else:
            return {
                "status": "failed",
                "email": email,
                "message": "Failed to extract API token"
            }


def load_credentials(file_path):
    """Load credentials dari file"""
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
                    print(f"[!] Baris {line_num}: Format salah (email:password)")
                    continue
                
                parts = line.split(':', 1)
                email, password = parts
                email = email.strip()
                password = password.strip()
                
                if not email or not password:
                    print(f"[!] Baris {line_num}: Email atau password kosong")
                    continue
                
                credentials.append({
                    "email": email,
                    "password": password
                })
                print(f"[✓] Baris {line_num}: {email} loaded")
        
        print(f"\n[✓] Total {len(credentials)} credential(s) loaded\n")
        return credentials
    
    except Exception as e:
        print(f"[✗] Error loading file: {e}")
        return credentials


def main():
    """Main function"""
    print("\n" + "=" * 70)
    print("WPScan API Token Extractor - Batch Mode")
    print("=" * 70 + "\n")
    
    while True:
        print("[1] Load credentials dari file")
        print("[2] Input manual")
        print("[3] Exit")
        
        mode = input("\nPilih mode (1-3): ").strip()
        
        if mode == "3":
            print("\n[✓] Sampai jumpa!\n")
            break
        
        if mode == "1":
            file_path = input("📁 Path file (format: email:password): ").strip()
            
            if not file_path:
                print("[!] Path tidak boleh kosong\n")
                continue
            
            credentials = load_credentials(file_path)
            
            if not credentials:
                print("[!] Tidak ada credentials valid\n")
                continue
            
            # Input delay
            try:
                delay_input = input("⏱️  Delay antar pengecekan (detik, default: 3): ").strip()
                delay = int(delay_input) if delay_input else 3
            except ValueError:
                delay = 3
            
            print(f"\n[→] Starting batch extract...")
            print(f"[→] Total akun: {len(credentials)}")
            print(f"[→] Delay: {delay} detik\n")
            
            results = []
            
            for idx, cred in enumerate(credentials, 1):
                print(f"\n{'=' * 70}")
                print(f"Account {idx}/{len(credentials)}")
                print(f"{'=' * 70}")
                
                checker = WPScanChecker()
                result = checker.check_account(
                    email=cred['email'],
                    password=cred['password'],
                    remember_me=False
                )
                
                results.append(result)
                
                # Delay
                if idx < len(credentials):
                    print(f"\n[⏳] Waiting {delay} seconds...")
                    for i in range(delay, 0, -1):
                        print(f"[⏳] {i}s...", end='\r')
                        time.sleep(1)
                    print(" " * 20, end='\r')
            
            # Summary
            print(f"\n{'=' * 70}")
            print("BATCH COMPLETE")
            print(f"{'=' * 70}")
            print(f"Total: {len(credentials)}")
            print(f"Success: {len([r for r in results if r['status'] == 'success'])}")
            print(f"Failed: {len([r for r in results if r['status'] == 'failed'])}")
        
        elif mode == "2":
            email = input("\n📧 Email: ").strip()
            password = input("🔐 Password: ").strip()
            
            if not email or not password:
                print("[!] Email dan password harus diisi\n")
                continue
            
            checker = WPScanChecker()
            result = checker.check_account(email, password, remember_me=False)
            
            print("\n" + "=" * 70)
            print("RESULT:")
            print("=" * 70)
            print(json.dumps(result, indent=2))
            print("=" * 70 + "\n")
        
        else:
            print("[!] Pilihan tidak valid\n")


if __name__ == "__main__":
    main()
