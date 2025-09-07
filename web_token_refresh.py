#!/usr/bin/env python3
"""
Web-based amoCRM Token Refresh Interface

This creates a simple web interface for refreshing amoCRM tokens.
Can be run locally or deployed to Heroku for easy token management.

Usage:
- Local: python web_token_refresh.py
- Heroku: Access via your Heroku app URL + /refresh-tokens

Environment Variables Required:
- AMOCRM_CLIENT_ID
- AMOCRM_CLIENT_SECRET  
- AMOCRM_SUBDOMAIN
- AMOCRM_REDIRECT_URL
"""

import os
import requests
import json
import logging
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# HTML template for the token refresh page
TOKEN_REFRESH_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>amoCRM Token Refresh</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .warning { background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .info { background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .btn { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin: 10px 5px 0 0; }
        .btn:hover { background: #0056b3; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .btn-success { background: #28a745; }
        .btn-success:hover { background: #218838; }
        .code { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 5px; padding: 15px; font-family: monospace; margin: 10px 0; word-break: break-all; }
        .status { margin: 20px 0; padding: 15px; border-radius: 5px; }
        h1 { color: #333; margin-bottom: 30px; }
        h2 { color: #666; margin-top: 30px; margin-bottom: 15px; }
        .step { margin: 20px 0; padding: 15px; border-left: 4px solid #007bff; background: #f8f9fa; }
        input[type="text"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; margin: 5px 0; }
        label { font-weight: bold; margin-top: 15px; display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔑 amoCRM Token Refresh</h1>
        
        {% if message %}
            <div class="{{ message_type }}">{{ message | safe }}</div>
        {% endif %}
        
        {% if not auth_code %}
            <div class="info">
                <strong>Current Status:</strong><br>
                Refresh token has expired and needs manual renewal.
            </div>
            
            <h2>Step 1: Get Authorization Code</h2>
            <div class="step">
                <p><strong>Click the button below to authorize the application:</strong></p>
                <a href="{{ auth_url }}" class="btn" target="_blank">🔗 Authorize Application</a>
                <p><small>This will open amoCRM authorization in a new tab</small></p>
            </div>
            
            <h2>Step 2: Enter Authorization Code</h2>
            <div class="step">
                <form method="post">
                    <label for="auth_code">After authorization, paste the code from the redirect URL:</label>
                    <input type="text" name="auth_code" id="auth_code" placeholder="Enter authorization code here..." required>
                    <br><br>
                    <button type="submit" class="btn btn-success">🔄 Refresh Tokens</button>
                </form>
            </div>
            
            <div class="warning">
                <strong>Instructions:</strong>
                <ol>
                    <li>Click "Authorize Application" above</li>
                    <li>Login to amoCRM and authorize the integration</li>
                    <li>You'll be redirected to a URL with a 'code' parameter</li>
                    <li>Copy the code value and paste it in the form above</li>
                    <li>Click "Refresh Tokens" to complete the process</li>
                </ol>
            </div>
            
        {% else %}
            <h2>Step 3: Processing Authorization</h2>
            <div class="step">
                <p>Processing authorization code: <code>{{ auth_code[:20] }}...</code></p>
            </div>
        {% endif %}
        
        {% if config_status %}
            <h2>Configuration Status</h2>
            <div class="status">
                {{ config_status | safe }}
            </div>
        {% endif %}
        
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 14px;">
            <p><strong>Need help?</strong> This interface helps refresh expired amoCRM tokens. 
            After successful refresh, tokens will be saved to both files and Heroku config vars.</p>
        </div>
    </div>
</body>
</html>
'''

def get_amocrm_config():
    """Get amoCRM configuration from environment"""
    config = {
        'subdomain': os.getenv('AMOCRM_SUBDOMAIN'),
        'client_id': os.getenv('AMOCRM_CLIENT_ID'),
        'client_secret': os.getenv('AMOCRM_CLIENT_SECRET'),
        'redirect_url': os.getenv('AMOCRM_REDIRECT_URL')
    }
    
    missing = [key for key, value in config.items() if not value]
    if missing:
        return None, f"Missing environment variables: {', '.join(missing)}"
    
    return config, None

def generate_auth_url(config):
    """Generate authorization URL"""
    return (
        f"https://{config['subdomain']}.amocrm.ru/oauth2/access_token?"
        f"client_id={config['client_id']}&"
        f"redirect_uri={config['redirect_url']}&"
        f"response_type=code&"
        f"scope=crm"
    )

def exchange_code_for_tokens(config, auth_code):
    """Exchange authorization code for tokens"""
    token_url = f"https://{config['subdomain']}.amocrm.ru/oauth2/access_token"
    
    data = {
        "client_id": config['client_id'],
        "client_secret": config['client_secret'],
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": config['redirect_url'],
    }
    
    try:
        logging.info("Requesting new tokens from amoCRM...")
        response = requests.post(token_url, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")
            expires_in = result.get("expires_in", 86400)
            
            if not access_token or not refresh_token:
                return None, "Tokens not found in response"
            
            # Save tokens to files
            with open("access_token.txt", "w", encoding='utf-8') as f:
                f.write(access_token)
            
            with open("refresh_token.txt", "w", encoding='utf-8') as f:
                f.write(refresh_token)
            
            logging.info("✅ New tokens saved successfully!")
            
            return {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_in': expires_in
            }, None
            
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logging.error(f"Token exchange failed: {error_msg}")
            return None, error_msg
            
    except requests.RequestException as e:
        error_msg = f"Network error: {e}"
        logging.error(error_msg)
        return None, error_msg

def update_heroku_config_vars(tokens):
    """Update Heroku config vars with new tokens (if running on Heroku)"""
    heroku_app_name = os.getenv('HEROKU_APP_NAME')
    heroku_api_key = os.getenv('HEROKU_API_KEY')
    
    if not heroku_app_name or not heroku_api_key:
        return "Heroku credentials not configured (this is optional)"
    
    try:
        headers = {
            'Authorization': f'Bearer {heroku_api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.heroku+json; version=3'
        }
        
        config_vars = {
            'AMOCRM_ACCESS_TOKEN': tokens['access_token'],
            'AMOCRM_REFRESH_TOKEN': tokens['refresh_token']
        }
        
        url = f'https://api.heroku.com/apps/{heroku_app_name}/config-vars'
        response = requests.patch(url, headers=headers, json=config_vars, timeout=30)
        
        if response.status_code == 200:
            return "✅ Heroku config vars updated successfully"
        else:
            return f"⚠️ Heroku update failed: {response.status_code} - {response.text}"
            
    except Exception as e:
        return f"⚠️ Heroku update error: {e}"

@app.route('/')
@app.route('/refresh-tokens', methods=['GET', 'POST'])
def refresh_tokens():
    """Main token refresh interface"""
    
    # Get configuration
    config, config_error = get_amocrm_config()
    if not config:
        return render_template_string(TOKEN_REFRESH_TEMPLATE, 
                                    message=f"Configuration Error: {config_error}",
                                    message_type="error")
    
    config_status = "✅ amoCRM configuration loaded successfully"
    auth_url = generate_auth_url(config)
    
    # Handle form submission
    if request.method == 'POST':
        auth_code = request.form.get('auth_code', '').strip()
        
        if not auth_code:
            return render_template_string(TOKEN_REFRESH_TEMPLATE,
                                        message="Please enter an authorization code",
                                        message_type="error",
                                        auth_url=auth_url,
                                        config_status=config_status)
        
        # Exchange code for tokens
        tokens, token_error = exchange_code_for_tokens(config, auth_code)
        
        if not tokens:
            return render_template_string(TOKEN_REFRESH_TEMPLATE,
                                        message=f"Token Exchange Failed: {token_error}",
                                        message_type="error", 
                                        auth_url=auth_url,
                                        config_status=config_status,
                                        auth_code=auth_code)
        
        # Update Heroku config vars
        heroku_status = update_heroku_config_vars(tokens)
        
        success_message = (
            f"🎉 <strong>Token Refresh Successful!</strong><br><br>"
            f"✅ Access Token: {tokens['access_token'][:20]}...<br>"
            f"✅ Refresh Token: {tokens['refresh_token'][:20]}...<br>"
            f"✅ Expires in: {tokens['expires_in']} seconds ({tokens['expires_in']//3600} hours)<br>"
            f"✅ Tokens saved to files<br>"
            f"{heroku_status}<br><br>"
            f"<strong>Next Steps:</strong><br>"
            f"1. Test the bot - try creating a new lead<br>"
            f"2. Process any backup leads with: <code>python retry_backup_leads.py</code><br>"
            f"3. Your bot should now work normally!"
        )
        
        return render_template_string(TOKEN_REFRESH_TEMPLATE,
                                    message=success_message,
                                    message_type="success",
                                    config_status=config_status)
    
    # Show initial form
    return render_template_string(TOKEN_REFRESH_TEMPLATE,
                                auth_url=auth_url,
                                config_status=config_status)

@app.route('/status')
def status():
    """Check current token status"""
    try:
        # Check if tokens exist
        access_token = None
        refresh_token = None
        
        if os.path.exists("access_token.txt"):
            with open("access_token.txt", "r") as f:
                access_token = f.read().strip()
        
        if os.path.exists("refresh_token.txt"):
            with open("refresh_token.txt", "r") as f:
                refresh_token = f.read().strip()
        
        status_info = {
            "timestamp": datetime.now().isoformat(),
            "access_token_exists": bool(access_token),
            "refresh_token_exists": bool(refresh_token),
            "access_token_length": len(access_token) if access_token else 0,
            "refresh_token_length": len(refresh_token) if refresh_token else 0
        }
        
        return jsonify(status_info)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print(f"🌐 Starting amoCRM Token Refresh Server on port {port}")
    print(f"🔗 Access at: http://localhost:{port}/refresh-tokens")
    
    app.run(host='0.0.0.0', port=port, debug=debug)