#!/usr/bin/env python3
"""
Test script for amoCRM integration
This script helps debug amoCRM connection issues independently.
"""

import os
import requests
import json
import logging
from os.path import exists
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("amocrm_test.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def load_amocrm_config():
    """Load amoCRM configuration from environment or files"""
    load_dotenv()
    
    # Try to load from environment first
    access_token = os.getenv("AMOCRM_ACCESS_TOKEN")
    refresh_token = os.getenv("AMOCRM_REFRESH_TOKEN")
    
    # Fallback to token files
    if not access_token and exists("access_token.txt"):
        with open("access_token.txt", "r", encoding='utf-8') as f:
            access_token = f.read().strip()
        logging.info("Loaded access token from file")
    
    if not refresh_token and exists("refresh_token.txt"):
        with open("refresh_token.txt", "r", encoding='utf-8') as f:
            refresh_token = f.read().strip()
        logging.info("Loaded refresh token from file")
    
    # Get other configuration
    subdomain = os.getenv("AMOCRM_SUBDOMAIN")
    client_id = os.getenv("AMOCRM_CLIENT_ID")
    client_secret = os.getenv("AMOCRM_CLIENT_SECRET")
    redirect_url = os.getenv("AMOCRM_REDIRECT_URL")
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'subdomain': subdomain,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_url': redirect_url
    }

def test_account_access(config):
    """Test basic account access"""
    if not config['subdomain'] or not config['access_token']:
        logging.error("Missing subdomain or access token")
        return False
    
    base_url = f"https://{config['subdomain']}.amocrm.ru/api/v4"
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json",
    }
    
    try:
        logging.info("Testing account access...")
        response = requests.get(f"{base_url}/account", headers=headers, timeout=10)
        
        if response.status_code == 200:
            account_data = response.json()
            logging.info(f"✅ Account access successful!")
            logging.info(f"Account name: {account_data.get('name', 'N/A')}")
            logging.info(f"Account ID: {account_data.get('id', 'N/A')}")
            return True
        elif response.status_code == 401:
            logging.error("❌ Unauthorized - token may be expired")
            logging.info("Response:", response.text)
            return False
        else:
            logging.error(f"❌ Error {response.status_code}: {response.text}")
            return False
            
    except requests.RequestException as e:
        logging.error(f"❌ Network error: {e}")
        return False

def test_create_test_contact(config):
    """Test creating a test contact"""
    if not config['subdomain'] or not config['access_token']:
        return False
        
    base_url = f"https://{config['subdomain']}.amocrm.ru/api/v4"
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json",
    }
    
    # Test contact data
    contact_data = [{
        "name": "Test Contact (Delete me)",
        "responsible_user_id": 12208190,
        "custom_fields_values": [
            {
                "field_code": "PHONE",
                "values": [{"value": "+82 10 1234 5678", "enum_code": "WORK"}]
            }
        ]
    }]
    
    try:
        logging.info("Testing contact creation...")
        response = requests.post(f"{base_url}/contacts", headers=headers, json=contact_data, timeout=10)
        
        if response.status_code in [200, 201]:
            result = response.json()
            contact_id = None
            if 'id' in result:
                contact_id = result['id']
            elif '_embedded' in result and 'contacts' in result['_embedded']:
                contacts = result['_embedded']['contacts']
                if contacts:
                    contact_id = contacts[0].get('id')
            
            if contact_id:
                logging.info(f"✅ Test contact created successfully! ID: {contact_id}")
                return True
            else:
                logging.warning("Contact created but ID not found in response")
                logging.info(f"Response: {response.text}")
                return False
        else:
            logging.error(f"❌ Failed to create test contact: {response.status_code}")
            logging.info(f"Response: {response.text}")
            return False
            
    except requests.RequestException as e:
        logging.error(f"❌ Network error during contact creation: {e}")
        return False

def main():
    """Main test function"""
    print("🔍 Testing amoCRM Integration")
    print("=" * 40)
    
    # Load configuration
    config = load_amocrm_config()
    
    # Check configuration
    missing_fields = []
    for key, value in config.items():
        if not value:
            missing_fields.append(key)
    
    if missing_fields:
        logging.error(f"❌ Missing configuration: {', '.join(missing_fields)}")
        logging.info("Please check your .env file or token files")
        return False
    
    logging.info("✅ Configuration loaded successfully")
    
    # Test account access
    if not test_account_access(config):
        logging.error("❌ Account access failed - cannot proceed with other tests")
        return False
    
    # Test contact creation
    if not test_create_test_contact(config):
        logging.error("❌ Contact creation test failed")
        return False
    
    logging.info("✅ All tests passed! amoCRM integration is working correctly.")
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)