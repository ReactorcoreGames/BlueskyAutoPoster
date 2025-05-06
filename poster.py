import csv
import json
import os
import sys
import base64
import requests
from datetime import datetime

CSV_FILE = 'posts.csv'
STATE_FILE = 'state.json'

BLUESKY_HANDLE = os.environ.get('BLUESKY_HANDLE')
BLUESKY_APP_PASSWORD = os.environ.get('BLUESKY_APP_PASSWORD')
REPO_ACTOR = os.environ.get('GITHUB_ACTOR')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
    print("Missing BLUESKY_HANDLE or BLUESKY_APP_PASSWORD env vars.")
    sys.exit(1)

# Load CSV
with open(CSV_FILE, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    posts = list(reader)

if not posts:
    print("No posts found in CSV.")
    sys.exit(0)

# Load state
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, encoding='utf-8') as f:
        state = json.load(f)
    last_index = state.get('last_row_index', -1)
else:
    last_index = -1

# Get next post
next_index = (last_index + 1) % len(posts)
post = posts[next_index]

title = post['title'].strip()
url = post['url'].strip()
hashtags = post['hashtags'].strip()

content = f"{title}\n\n{url}\n\n{hashtags}"

if len(content) > 300:
    print(f"Warning: Post at row {next_index + 2} exceeds 300 chars. Trimming hashtags.")
    content = f"{title}\n\n{url}\n\n"
    # Leave hashtags out if over budget

print(f"Posting row {next_index + 2}: {content}")

# Bluesky API: create post
session = requests.Session()
session.auth = (BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

# Get session
resp = session.post('https://bsky.social/xrpc/com.atproto.server.createSession', json={
    'identifier': BLUESKY_HANDLE,
    'password': BLUESKY_APP_PASSWORD
})
resp.raise_for_status()
access_jwt = resp.json()['accessJwt']

# Post the status
headers = {
    'Authorization': f'Bearer {access_jwt}',
    'Content-Type': 'application/json'
}
post_data = {
    "$type": "app.bsky.feed.post",
    "text": content,
    "createdAt": datetime.utcnow().isoformat() + 'Z'
}
resp = session.post('https://bsky.social/xrpc/com.atproto.repo.createRecord', headers=headers, json={
    "collection": "app.bsky.feed.post",
    "repo": BLUESKY_HANDLE,
    "record": post_data
})
resp.raise_for_status()
print("Post successful!")

# Update state
new_state = {
    'last_row_index': next_index,
    'last_post_time': datetime.utcnow().isoformat() + 'Z'
}
with open(STATE_FILE, 'w', encoding='utf-8') as f:
    json.dump(new_state, f, indent=2)
print(f"State updated: {new_state}")

# Commit state.json back to repo
commit_message = f'Update state.json after posting row {next_index + 2}'
cmds = [
    'git config user.name "{}"'.format(REPO_ACTOR),
    'git config user.email "{}@users.noreply.github.com"'.format(REPO_ACTOR),
    'git add {}'.format(STATE_FILE),
    'git commit -m "{}"'.format(commit_message),
    'git push'
]
for cmd in cmds:
    print(f"Running: {cmd}")
    os.system(cmd)
