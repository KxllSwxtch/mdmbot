#!/usr/bin/env python3
"""
Update Heroku Config Variables Script

This script helps update Heroku config variables with new amoCRM tokens.
Useful when you need to programmatically update tokens on Heroku.

Prerequisites:
1. Heroku API Key (get from: heroku auth:token)
2. Heroku App Name

Usage:
    python update_heroku_tokens.py

Environment Variables:
    HEROKU_API_KEY - Your Heroku API key
    HEROKU_APP_NAME - Your Heroku app name (e.g., 'my-telegram-bot')

You can also set these interactively when running the script.
"""

import os
import requests
import json
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("heroku_update.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def get_heroku_credentials():
    """Get Heroku API credentials"""
    api_key = os.getenv('HEROKU_API_KEY')
    app_name = os.getenv('HEROKU_APP_NAME')
    
    if not api_key:
        print("\\n🔑 Heroku API Key not found in environment variables")
        print("Get your API key by running: heroku auth:token")
        api_key = input("Enter your Heroku API key: ").strip()
    
    if not app_name:
        print("\\n📱 Heroku App Name not found in environment variables")
        app_name = input("Enter your Heroku app name: ").strip()
    
    return api_key, app_name

def get_current_tokens():
    """Load current tokens from files"""
    access_token = None
    refresh_token = None
    
    try:
        if os.path.exists("access_token.txt"):
            with open("access_token.txt", "r", encoding='utf-8') as f:
                access_token = f.read().strip()
                
        if os.path.exists("refresh_token.txt"):
            with open("refresh_token.txt", "r", encoding='utf-8') as f:
                refresh_token = f.read().strip()
                
        return access_token, refresh_token
        
    except Exception as e:
        logging.error(f"Error reading token files: {e}")
        return None, None

def get_heroku_config_vars(api_key, app_name):
    """Get current Heroku config variables"""
    url = f'https://api.heroku.com/apps/{app_name}/config-vars'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/vnd.heroku+json; version=3'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            return response.json(), None
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            return None, error_msg
            
    except requests.RequestException as e:
        return None, f"Network error: {e}"

def update_heroku_config_vars(api_key, app_name, config_vars):
    """Update Heroku config variables"""
    url = f'https://api.heroku.com/apps/{app_name}/config-vars'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/vnd.heroku+json; version=3'
    }
    
    try:
        logging.info(f"Updating config vars for app: {app_name}")
        response = requests.patch(url, headers=headers, json=config_vars, timeout=30)
        
        if response.status_code == 200:
            return response.json(), None
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            return None, error_msg
            
    except requests.RequestException as e:
        return None, f"Network error: {e}"

def show_config_comparison(current_config, new_tokens):
    """Show comparison between current and new config"""
    print("\\n📋 Configuration Comparison:")
    print("=" * 50)
    
    # Current tokens
    current_access = current_config.get('AMOCRM_ACCESS_TOKEN', 'Not set')
    current_refresh = current_config.get('AMOCRM_REFRESH_TOKEN', 'Not set')
    
    print(f"Current Access Token:  {current_access[:20] if current_access != 'Not set' else 'Not set'}...")
    print(f"New Access Token:      {new_tokens['AMOCRM_ACCESS_TOKEN'][:20]}...")
    print()
    print(f"Current Refresh Token: {current_refresh[:20] if current_refresh != 'Not set' else 'Not set'}...")
    print(f"New Refresh Token:     {new_tokens['AMOCRM_REFRESH_TOKEN'][:20]}...")
    print()

def validate_tokens(access_token, refresh_token):
    """Basic token validation"""
    if not access_token or len(access_token) < 10:
        return False, "Access token is too short or empty"
    
    if not refresh_token or len(refresh_token) < 10:
        return False, "Refresh token is too short or empty"
    
    return True, None

def main():
    """Main function"""
    print("🚀 Heroku Config Variables Update Tool")
    print("=" * 40)
    
    # Get Heroku credentials
    api_key, app_name = get_heroku_credentials()
    
    if not api_key or not app_name:
        print("❌ Missing Heroku credentials. Cannot proceed.")
        return False
    
    print(f"\\n🎯 Target App: {app_name}")
    
    # Get current tokens from files
    print("\\n📂 Loading tokens from files...")
    access_token, refresh_token = get_current_tokens()
    
    if not access_token or not refresh_token:
        print("❌ Could not load tokens from files.")
        print("   Make sure access_token.txt and refresh_token.txt exist.")
        print("   Run get_new_tokens.py first to obtain tokens.")
        return False
    
    # Validate tokens
    is_valid, validation_error = validate_tokens(access_token, refresh_token)
    if not is_valid:
        print(f"❌ Token validation failed: {validation_error}")
        return False
    
    print("✅ Tokens loaded and validated")
    
    # Get current Heroku config
    print("\\n🔍 Getting current Heroku configuration...")
    current_config, config_error = get_heroku_config_vars(api_key, app_name)
    
    if not current_config:
        print(f"❌ Failed to get current config: {config_error}")
        return False
    
    print("✅ Current configuration retrieved")
    
    # Prepare new config vars
    new_tokens = {
        'AMOCRM_ACCESS_TOKEN': access_token,
        'AMOCRM_REFRESH_TOKEN': refresh_token
    }
    
    # Show comparison
    show_config_comparison(current_config, new_tokens)
    
    # Confirm update
    confirm = input("\\n❓ Update Heroku config variables? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Update cancelled by user")
        return False
    
    # Update config vars
    print("\\n🔄 Updating Heroku config variables...")
    updated_config, update_error = update_heroku_config_vars(api_key, app_name, new_tokens)
    
    if not updated_config:
        print(f"❌ Update failed: {update_error}")
        return False
    
    print("✅ Heroku config variables updated successfully!")
    
    # Show updated values
    print("\\n🎉 Update Summary:")
    print("=" * 30)
    print(f"Access Token: {new_tokens['AMOCRM_ACCESS_TOKEN'][:20]}... ✅")
    print(f"Refresh Token: {new_tokens['AMOCRM_REFRESH_TOKEN'][:20]}... ✅")
    
    print("\\n📋 Next Steps:")
    print("1. Restart your Heroku app: heroku restart")
    print("2. Test the bot by creating a new lead")
    print("3. Process backup leads: python retry_backup_leads.py")
    print("4. Monitor logs: heroku logs --tail")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)