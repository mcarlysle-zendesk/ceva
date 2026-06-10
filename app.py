import os
import sys
import json
import requests

# 1. Load credentials from GitHub Actions secrets environment
ZENDESK_SUBDOMAIN = os.environ.get("ZENDESK_SUBDOMAIN")
ZENDESK_EMAIL = os.environ.get("ZENDESK_EMAIL")
ZENDESK_API_TOKEN = os.environ.get("ZENDESK_API_TOKEN")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL")

# 2. Extract incoming data sent by Zendesk via GitHub's event path
event_path = os.environ.get("GITHUB_EVENT_PATH")
if not event_path:
    print("Error: Missing event path data.")
    sys.exit(1)

with open(event_path, 'r') as f:
    event_data = json.load(f)

# Extract custom variables passed inside client_payload
payload = event_data.get("client_payload", {})
ticket_id = payload.get("ticket_id")
subject = payload.get("subject", "New Ticket")

if not ticket_id:
    print("Error: No ticket_id provided in the payload.")
    sys.exit(1)

AUTH = (f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN)
BASE_URL = f"https://{ZENDESK_SUBDOMAIN}://"

try:
    # 3. Fetch latest comment attachments
    comments_url = f"{BASE_URL}/tickets/{ticket_id}/comments.json"
    comments_res = requests.get(comments_url, auth=AUTH)
    comments_res.raise_for_status()
    
    latest_comment = comments_res.json()["comments"][-1]
    attachments = latest_comment.get("attachments", [])
    
    if not attachments:
        print("No attachments found. Task completed.")
        sys.exit(0)

    side_conv_attachment_ids = []

    # 4. Download and upload attachments to get Side Conversation tokens
    for att in attachments:
        file_url = att["content_url"]
        file_name = att["file_name"]
        content_type = att["content_type"]
        
        file_data = requests.get(file_url, auth=AUTH, stream=True).content
        
        upload_url = f"{BASE_URL}/tickets/{ticket_id}/side_conversations/attachments"
        files = {'file': (file_name, file_data, content_type)}
        
        upload_res = requests.post(upload_url, auth=AUTH, files=files)
        upload_res.raise_for_status()
        
        token_id = upload_res.json()["attachment"]["id"]
        side_conv_attachment_ids.append(token_id)

    # 5. Fire Side Conversation
    side_conv_url = f"{BASE_URL}/tickets/{ticket_id}/side_conversations"
    payload_data = {
        "message": {
            "subject": f"Automated GitHub Forward: {subject}",
            "body": "Please review the attached documents forwarded automatically from the customer ticket.",
            "to": [{"email": TARGET_EMAIL}],
            "attachment_ids": side_conv_attachment_ids
        }
    }
    
    conv_res = requests.post(side_conv_url, auth=AUTH, json=payload_data)
    conv_res.raise_for_status()
    print("Side conversation successfully created.")

except Exception as e:
    print(f"Execution Error: {str(e)}")
    sys.exit(1)
