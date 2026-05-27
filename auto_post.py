# This script publishes a post to Blogspot using the Blogger API.
# It will be called by GitHub Actions after generating a post.

import sys
import os
import json
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/blogger']
BLOG_ID = os.environ.get('BLOG_ID')  # Set this as a GitHub secret or env var

# Credentials from environment or secrets
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('GOOGLE_REFRESH_TOKEN')

def get_access_token():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token

def publish_to_blogspot(html_file):
    if not BLOG_ID:
        print("BLOG_ID environment variable not set.")
        sys.exit(1)
    access_token = get_access_token()
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    # Use filename as title
    title = os.path.basename(html_file).split('-', 1)[-1].replace('.html', '').replace('-', ' ').title()
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    data = {
        'kind': 'blogger#post',
        'title': title,
        'content': content,
    }
    resp = requests.post(url, headers=headers, data=json.dumps(data))
    if resp.status_code == 200:
        print(f"Successfully published post: {title}")
    else:
        print(f"Failed to publish post: {resp.status_code} {resp.text}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python publish_post.py <html_file>")
        sys.exit(1)
    publish_to_blogspot(sys.argv[1])
