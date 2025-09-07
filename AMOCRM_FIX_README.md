# amoCRM Token Expiry Fix

## 🔍 Problem
The bot is showing "❌ Произошла ошибка при отправке заявки" because the amoCRM refresh token has expired. The logs show:

```
ERROR - Ошибка при обновлении токена: 401, {"hint":"Token has expired","title":"Некорректный запрос"}
```

## ✅ Solution

### Step 1: Get New Tokens
1. Run the token refresh script:
   ```bash
   python get_new_tokens.py
   ```

2. Follow the instructions to:
   - Visit the authorization URL
   - Authorize the application in amoCRM
   - Copy the authorization code from the redirect URL
   - Paste it into the script

3. The script will save new tokens to `access_token.txt` and `refresh_token.txt`

### Step 2: Process Backup Leads
1. After getting new tokens, retry failed leads:
   ```bash
   python retry_backup_leads.py
   ```

2. This will process all leads that were saved to backup during the outage

### Step 3: Deploy to Heroku
1. Commit the changes:
   ```bash
   git add .
   git commit -m "Fix amoCRM token expiry and add backup system"
   ```

2. Deploy to Heroku:
   ```bash
   git push heroku main
   ```

3. Update environment variables on Heroku (if using env vars instead of files):
   ```bash
   heroku config:set AMOCRM_ACCESS_TOKEN="your_new_token"
   heroku config:set AMOCRM_REFRESH_TOKEN="your_new_refresh_token"
   ```

## 🔧 What Was Fixed

### 1. **Token Management**
- ✅ Fixed token loading to fallback to files when env vars are missing
- ✅ Added better error messages for token issues
- ✅ Added token validation before API calls

### 2. **Backup System**
- ✅ Leads are now saved to `backup_leads.json` when amoCRM fails
- ✅ Users get a better message explaining the issue
- ✅ Admin notification system for token expiry

### 3. **Recovery Tools**
- ✅ `get_new_tokens.py` - Manual token refresh script
- ✅ `retry_backup_leads.py` - Process backup leads after fixing tokens
- ✅ `test_amocrm.py` - Test amoCRM connection

### 4. **Improved Error Handling**
- ✅ Better user messages during outages
- ✅ Comprehensive logging for debugging
- ✅ Graceful fallback to backup storage

## 📋 Environment Configuration

Make sure your `.env` file (or Heroku config vars) contains:

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token

# amoCRM Configuration
AMOCRM_SUBDOMAIN=your_subdomain
AMOCRM_CLIENT_ID=your_client_id
AMOCRM_CLIENT_SECRET=your_client_secret
AMOCRM_REDIRECT_URL=https://your-domain.com/callback

# Optional: For admin notifications
ADMIN_CHAT_ID=your_telegram_chat_id
```

## 🚨 Prevention

To avoid this issue in the future:

1. **Set up monitoring**: Use the `ADMIN_CHAT_ID` to get notifications when tokens expire
2. **Regular token refresh**: amoCRM tokens expire every 24 hours for access tokens, and refresh tokens can expire after extended periods of inactivity
3. **Automated alerts**: Consider setting up a cron job to check token status

## 📊 Backup Lead Format

Backup leads are stored in `backup_leads.json`:

```json
[
  {
    "timestamp": "2025-09-07T10:30:00",
    "name": "Customer Name",
    "phone": "+1234567890",
    "budget": "50000",
    "car_link": "https://encar.com/...",
    "user_id": 123456789,
    "status": "pending"
  }
]
```

## 🔄 Recovery Process

1. **Immediate**: Leads are saved to backup when amoCRM fails
2. **User notification**: Users are informed their lead is saved
3. **Admin alert**: Admin gets notified about the issue
4. **Manual fix**: Admin runs `get_new_tokens.py`
5. **Recovery**: Admin runs `retry_backup_leads.py`
6. **Complete**: All backup leads are processed

This system ensures no leads are lost during amoCRM outages!