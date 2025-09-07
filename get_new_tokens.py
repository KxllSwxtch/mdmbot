#!/usr/bin/env python3
"""
Manual amoCRM Token Refresh Script

This script helps you manually obtain fresh amoCRM tokens when refresh tokens expire.
Run this script when you get "Token has expired" errors.

Usage:
1. Run: python get_new_tokens.py
2. Follow the instructions to get an authorization code from amoCRM
3. The script will save new tokens to access_token.txt and refresh_token.txt
"""

import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
        print("\\n📝 Next steps:")
        print("1. Restart your Telegram bot")
        print("2. Test sending a lead to verify it works")
        print("\\n💡 Tip: Set up monitoring to avoid token expiry in the future")
        return True
    else:
        print("\\n❌ Token refresh failed. Please try again or check your configuration.")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)