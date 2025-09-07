#!/usr/bin/env python3
"""
Retry Backup Leads Script

This script processes leads that failed to be sent to amoCRM and retries sending them.
Run this after fixing amoCRM connection issues to process accumulated leads.

Usage:
1. Fix amoCRM tokens using get_new_tokens.py
2. Run: python retry_backup_leads.py
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Import the create_amocrm_lead function from main.py
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("retry_leads.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def load_backup_leads():
    """Load backup leads from JSON file"""
    backup_file = "backup_leads.json"
    if not os.path.exists(backup_file):
        logging.info("No backup leads file found")
        return []
    
    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            leads = json.load(f)
        logging.info(f"Loaded {len(leads)} leads from backup")
        return leads
    except Exception as e:
        logging.error(f"Error loading backup leads: {e}")
        return []

def save_backup_leads(leads):
    """Save backup leads back to JSON file"""
    try:
        with open("backup_leads.json", "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.error(f"Error saving backup leads: {e}")
        return False

def create_amocrm_lead_simple(name, phone, budget, car_link=None):
    """Simplified version of create_amocrm_lead for retry script"""
    import requests
    from os.path import exists
    
    # Load environment variables
    load_dotenv()
    
    def format_phone(phone):
        """Simple phone formatting"""
        import re
        clean_phone = re.sub(r'[^\d+]', '', phone)
        return clean_phone
    
    logging.info(f"Retrying lead: {name} - {phone}")
    
    try:
        price = int(float(budget))
    except (ValueError, TypeError):
        price = 0
    
    formatted_phone = format_phone(phone)
    
    # Try to get tokens from environment or files
    access_token = os.getenv("AMOCRM_ACCESS_TOKEN")
    refresh_token = os.getenv("AMOCRM_REFRESH_TOKEN")
    
    if not access_token and exists("access_token.txt"):
        with open("access_token.txt", "r", encoding="utf-8") as f:
            access_token = f.read().strip()
    
    if not refresh_token and exists("refresh_token.txt"):
        with open("refresh_token.txt", "r", encoding="utf-8") as f:
            refresh_token = f.read().strip()
    
    if not access_token or not refresh_token:
        logging.error("Missing tokens for amoCRM")
        return False
    
    subdomain = os.getenv("AMOCRM_SUBDOMAIN")
    client_id = os.getenv("AMOCRM_CLIENT_ID")
    client_secret = os.getenv("AMOCRM_CLIENT_SECRET")
    redirect_url = os.getenv("AMOCRM_REDIRECT_URL")
    
    if not all([subdomain, client_id, client_secret, redirect_url]):
        logging.error("Missing amoCRM configuration")
        return False
    
    base_url = f"https://{subdomain}.amocrm.ru/api/v4"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    # Test token validity first
    try:
        test_response = requests.get(f"{base_url}/account", headers=headers, timeout=10)
        if test_response.status_code == 401:
            logging.warning("Token expired, cannot retry leads. Please refresh tokens first.")
            return False
    except Exception as e:
        logging.error(f"Error testing token: {e}")
        return False
    
    # Create contact
    contact_data = [{
        "name": name,
        "responsible_user_id": 12208190,
        "custom_fields_values": [
            {
                "field_code": "PHONE",
                "values": [{"value": formatted_phone, "enum_code": "WORK"}]
            }
        ]
    }]
    
    try:
        contact_response = requests.post(f"{base_url}/contacts", headers=headers, json=contact_data, timeout=10)
        
        if contact_response.status_code >= 400:
            logging.error(f"Error creating contact: {contact_response.status_code}, {contact_response.text}")
            return False
        
        # Get contact ID
        contact_result = contact_response.json()
        contact_id = None
        if 'id' in contact_result:
            contact_id = contact_result['id']
        elif '_embedded' in contact_result and 'contacts' in contact_result['_embedded']:
            contacts = contact_result['_embedded']['contacts']
            if contacts:
                contact_id = contacts[0].get('id')
        
        if not contact_id:
            logging.error("Could not get contact ID")
            return False
        
        # Create lead
        lead_data = [{
            "name": f"Заявка от {name}",
            "price": price,
            "_embedded": {
                "contacts": [{"id": contact_id}],
                "tags": [{"name": "telegram_bot"}, {"name": "backup_retry"}]
            }
        }]
        
        lead_response = requests.post(f"{base_url}/leads", headers=headers, json=lead_data, timeout=10)
        
        if lead_response.status_code >= 400:
            logging.error(f"Error creating lead: {lead_response.status_code}, {lead_response.text}")
            return False
        
        # Get lead ID
        lead_result = lead_response.json()
        lead_id = None
        if 'id' in lead_result:
            lead_id = lead_result['id']
        elif '_embedded' in lead_result and 'leads' in lead_result['_embedded']:
            leads = lead_result['_embedded']['leads']
            if leads:
                lead_id = leads[0].get('id')
        
        if not lead_id:
            logging.error("Could not get lead ID")
            return False
        
        # Add note
        if car_link and car_link.lower() != "нет":
            note_text = f"Заявка из Telegram (ВОССТАНОВЛЕНА ИЗ РЕЗЕРВА)\\nФИО: {name}\\nТелефон: {formatted_phone}\\nБюджет: {price}₽\\nСсылка: {car_link}"
        else:
            note_text = f"Заявка из Telegram (ВОССТАНОВЛЕНА ИЗ РЕЗЕРВА)\\nФИО: {name}\\nТелефон: {formatted_phone}\\nБюджет: {price}₽"
        
        note_data = [{"entity_id": lead_id, "note_type": "common", "params": {"text": note_text}}]
        
        note_response = requests.post(f"{base_url}/leads/notes", headers=headers, json=note_data, timeout=10)
        
        if note_response.status_code >= 400:
            logging.warning(f"Could not add note: {note_response.status_code}")
        
        logging.info(f"✅ Lead successfully created in amoCRM: {lead_id}")
        return True
        
    except Exception as e:
        logging.error(f"Error processing lead: {e}")
        return False

def retry_backup_leads():
    """Process all pending backup leads"""
    leads = load_backup_leads()
    
    if not leads:
        logging.info("No backup leads to process")
        return
    
    pending_leads = [lead for lead in leads if lead.get("status") == "pending"]
    
    if not pending_leads:
        logging.info("No pending leads to retry")
        return
    
    logging.info(f"Found {len(pending_leads)} pending leads to retry")
    
    success_count = 0
    failed_count = 0
    
    for lead in leads:
        if lead.get("status") != "pending":
            continue
        
        name = lead.get("name", "")
        phone = lead.get("phone", "")
        budget = lead.get("budget", 0)
        car_link = lead.get("car_link", "нет")
        
        logging.info(f"Processing lead: {name} - {phone}")
        
        if create_amocrm_lead_simple(name, phone, budget, car_link):
            lead["status"] = "completed"
            lead["completed_at"] = datetime.now().isoformat()
            success_count += 1
            logging.info(f"✅ Successfully processed: {name}")
        else:
            failed_count += 1
            logging.error(f"❌ Failed to process: {name}")
    
    # Save updated leads
    if save_backup_leads(leads):
        logging.info(f"Backup leads file updated")
    
    logging.info(f"\\n📊 Retry Summary:")
    logging.info(f"✅ Successful: {success_count}")
    logging.info(f"❌ Failed: {failed_count}")
    logging.info(f"📝 Total processed: {success_count + failed_count}")
    
    # Show remaining pending leads
    remaining_pending = len([lead for lead in leads if lead.get("status") == "pending"])
    if remaining_pending > 0:
        logging.warning(f"⚠️ {remaining_pending} leads still pending (failed to process)")
    else:
        logging.info("🎉 All backup leads processed successfully!")

def main():
    """Main function"""
    print("🔄 Retrying Backup Leads")
    print("=" * 40)
    
    try:
        retry_backup_leads()
    except Exception as e:
        logging.error(f"Script error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)