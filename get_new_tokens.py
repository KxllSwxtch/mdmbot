#!/usr/bin/env python3
"""
Manual amoCRM Token Refresh Script (Enhanced)

This script helps you manually obtain fresh amoCRM tokens when refresh tokens expire.
Run this script when you get "Token has expired" errors.

Features:
- Interactive token refresh process
- Token validation after refresh
- Automatic Heroku config update (optional)
- Backup lead processing reminder

Usage:
1. Run: python get_new_tokens.py
2. Follow the instructions to get an authorization code from amoCRM
3. The script will save new tokens and optionally update Heroku config
"""

import os
import requests
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("token_refresh.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def get_authorization_url():
    """Generate amoCRM authorization URL"""
    client_id = os.getenv("AMOCRM_CLIENT_ID")
    subdomain = os.getenv("AMOCRM_SUBDOMAIN")
    redirect_url = os.getenv("AMOCRM_REDIRECT_URL")
    
    if not all([client_id, subdomain, redirect_url]):
        print("❌ Missing environment variables. Please check your .env file.")
        print("Required: AMOCRM_CLIENT_ID, AMOCRM_SUBDOMAIN, AMOCRM_REDIRECT_URL")
        return None
    
    # OAuth2 authorization URL
    auth_url = (
        f"https://{subdomain}.amocrm.ru/oauth2/access_token?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_url}&"
        "response_type=code&"
        "scope=crm"
    )
    
    return auth_url

def exchange_code_for_tokens(auth_code):
    """Exchange authorization code for access and refresh tokens"""
    client_id = os.getenv("AMOCRM_CLIENT_ID")
    client_secret = os.getenv("AMOCRM_CLIENT_SECRET")
    subdomain = os.getenv("AMOCRM_SUBDOMAIN")
    redirect_url = os.getenv("AMOCRM_REDIRECT_URL")
    
    token_url = f"https://{subdomain}.amocrm.ru/oauth2/access_token"
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_url,
    }
    
    try:
        print("🔄 Requesting new tokens...")
        response = requests.post(token_url, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")
            expires_in = result.get("expires_in", 86400)  # Default 24 hours
            
            if not access_token or not refresh_token:
                print("❌ Tokens not found in response")
                print(f"Response: {response.text}")
                return False
            
            # Save tokens to files
            with open("access_token.txt", "w", encoding='utf-8') as f:
                f.write(access_token)
            
            with open("refresh_token.txt", "w", encoding='utf-8') as f:
                f.write(refresh_token)
            
            print("✅ New tokens saved successfully!")
            print(f"Access token expires in: {expires_in} seconds ({expires_in//3600} hours)")
            print(f"Access token (first 20 chars): {access_token[:20]}...")
            print(f"Refresh token (first 20 chars): {refresh_token[:20]}...")
            
            return True
        else:
            print(f"❌ Error getting tokens: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        return False

def validate_tokens_with_amocrm(access_token, subdomain):
    """Validate tokens by making a test API call"""
    test_url = f"https://{subdomain}.amocrm.ru/api/v4/account"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    try:
        logging.info("Validating new tokens with amoCRM API...")
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            account_data = response.json()
            logging.info("✅ Token validation successful!")
            return True, account_data.get('name', 'Unknown Account')
        else:
            logging.error(f"Token validation failed: {response.status_code}")
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except requests.RequestException as e:
        logging.error(f"Token validation network error: {e}")
        return False, f"Network error: {e}"

def update_heroku_tokens_optional(access_token, refresh_token):
    """Optionally update Heroku config vars with new tokens"""
    heroku_app_name = os.getenv('HEROKU_APP_NAME')
    heroku_api_key = os.getenv('HEROKU_API_KEY')
    
    if not heroku_app_name or not heroku_api_key:
        print("\n⚠️ Heroku credentials not found (HEROKU_APP_NAME, HEROKU_API_KEY)")
        print("Skipping Heroku config update...")
        return True
    
    try:
        print(f"\n🚀 Updating Heroku app: {heroku_app_name}")
        headers = {
            'Authorization': f'Bearer {heroku_api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.heroku+json; version=3'
        }
        
        config_vars = {
            'AMOCRM_ACCESS_TOKEN': access_token,
            'AMOCRM_REFRESH_TOKEN': refresh_token
        }
        
        url = f'https://api.heroku.com/apps/{heroku_app_name}/config-vars'
        response = requests.patch(url, headers=headers, json=config_vars, timeout=30)
        
        if response.status_code == 200:
            print("✅ Heroku config vars updated successfully!")
            return True
        else:
            print(f"⚠️ Heroku update failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"⚠️ Heroku update error: {e}")
        return False

def check_backup_leads():
    """Check if there are backup leads to process"""
    if os.path.exists("backup_leads.json"):
        try:
            with open("backup_leads.json", "r", encoding="utf-8") as f:
                leads = json.load(f)
            
            pending_leads = len([lead for lead in leads if lead.get("status") == "pending"])
            if pending_leads > 0:
                print(f"\n📝 Found {pending_leads} backup leads to process")
                print("   Run: python retry_backup_leads.py")
                return pending_leads
                
        except Exception as e:
            logging.warning(f"Error checking backup leads: {e}")
    
    return 0

def main():
    """Main function"""
    print("🔑 amoCRM Manual Token Refresh")
    print("=" * 40)
    
    # Generate authorization URL
    auth_url = get_authorization_url()
    if not auth_url:
        return False
    
    print(f"\\n📋 STEP 1: Visit this URL to authorize the application:")
    print(f"{auth_url}")
    
    print(f"\\n📋 STEP 2: After authorization, you'll be redirected to:")
    print(f"{os.getenv('AMOCRM_REDIRECT_URL')}")
    
    print(f"\\n📋 STEP 3: Copy the 'code' parameter from the redirected URL")
    print(f"Example: if redirected to 'https://example.com?code=ABC123&state=...'")
    print(f"Copy only the 'ABC123' part")
    
    print(f"\\n" + "="*40)
    auth_code = input("👆 Paste the authorization code here: ").strip()
    
    if not auth_code:
        print("❌ No authorization code provided")
        return False
    
    # Exchange code for tokens
    success = exchange_code_for_tokens(auth_code)
    
    if success:
        print("\\n🎉 Token refresh completed successfully!")
        
        # Validate tokens
        print("\\n🔍 Validating new tokens...")
        access_token = None
        if os.path.exists("access_token.txt"):
            with open("access_token.txt", "r", encoding='utf-8') as f:
                access_token = f.read().strip()
        
        if access_token:
            is_valid, account_info = validate_tokens_with_amocrm(access_token, os.getenv('AMOCRM_SUBDOMAIN'))
            if is_valid:
                print(f"✅ Token validation successful for account: {account_info}")
                
                # Optional Heroku update
                print("\\n🚀 Checking Heroku integration...")
                with open("refresh_token.txt", "r", encoding='utf-8') as f:
                    refresh_token = f.read().strip()
                
                update_heroku_tokens_optional(access_token, refresh_token)
            else:
                print(f"⚠️ Token validation failed: {account_info}")
        
        # Check for backup leads
        backup_count = check_backup_leads()
        
        print("\\n📝 Next steps:")
        print("1. Restart your Telegram bot (if on Heroku: heroku restart)")
        print("2. Test sending a lead to verify it works")
        if backup_count > 0:
            print(f"3. Process {backup_count} backup leads: python retry_backup_leads.py")
        print("\\n💡 Tip: Set up monitoring to avoid token expiry in the future")
        return True
    else:
        print("\\n❌ Token refresh failed. Please try again or check your configuration.")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)