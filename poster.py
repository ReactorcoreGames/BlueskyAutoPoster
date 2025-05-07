import csv
import json
import os
import sys
import requests
import re
from datetime import datetime, timezone

# Constants
CSV_FILE = 'posts.csv'
STATE_FILE = 'state.json'
BLUESKY_HANDLE = os.environ.get('BLUESKY_HANDLE')
BLUESKY_APP_PASSWORD = os.environ.get('BLUESKY_APP_PASSWORD')
REPO_ACTOR = os.environ.get('GITHUB_ACTOR', 'github-actions[bot]')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

def main():
    # Validate environment variables
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        print("Error: Missing BLUESKY_HANDLE or BLUESKY_APP_PASSWORD environment variables.")
        sys.exit(1)

    try:
        # Load CSV
        posts = load_posts()
        if not posts:
            print("No posts found in CSV.")
            sys.exit(0)

        # Load state
        state = load_state()
        last_index = state.get('last_row_index', -1)

        # Get next post
        next_index = (last_index + 1) % len(posts)
        post = posts[next_index]

        # Create post content
        content = create_post_content(post, next_index)

        # Post to Bluesky
        post_to_bluesky(content)

        # Update state
        update_state(next_index)

        # Commit changes back to repository
        commit_changes(next_index)

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def load_posts():
    """Load posts from CSV file."""
    try:
        with open(CSV_FILE, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except FileNotFoundError:
        print(f"Error: {CSV_FILE} not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        sys.exit(1)

def load_state():
    """Load state from JSON file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON in {STATE_FILE}. Starting from beginning.")
            return {}
        except Exception as e:
            print(f"Error reading state file: {str(e)}. Starting from beginning.")
            return {}
    return {}

def create_post_content(post, next_index):
    """Create formatted post content."""
    try:
        title = post.get('title', '').strip()
        url = post.get('url', '').strip()
        hashtags = post.get('hashtags', '').strip()

        if not title or not url:
            print(f"Error: Missing title or URL in row {next_index + 2}")
            sys.exit(1)

        content = f"{title}\n\n{url}\n\n{hashtags}"

        # Check for length constraints
        if len(content) > 300:
            print(f"Warning: Post at row {next_index + 2} exceeds 300 chars. Trimming hashtags.")
            # Try to keep as many hashtags as possible
            max_hashtags_length = 300 - len(f"{title}\n\n{url}\n\n")
            if max_hashtags_length > 0:
                trimmed_hashtags = hashtags[:max_hashtags_length].strip()
                content = f"{title}\n\n{url}\n\n{trimmed_hashtags}"
            else:
                content = f"{title}\n\n{url}"

        print(f"Posting row {next_index + 2}: {content}")
        return content

    except Exception as e:
        print(f"Error creating post content: {str(e)}")
        sys.exit(1)

def get_bluesky_auth():
    """Authenticate with Bluesky and return access token."""
    try:
        session = requests.Session()
        resp = session.post('https://bsky.social/xrpc/com.atproto.server.createSession', json={
            'identifier': BLUESKY_HANDLE,
            'password': BLUESKY_APP_PASSWORD
        })
        resp.raise_for_status()
        return resp.json()['accessJwt']
    except requests.RequestException as e:
        print(f"Error authenticating with Bluesky: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        sys.exit(1)

def extract_url_facets(content):
    """Extract URL facets for Bluesky rich text."""
    url_pattern = re.compile(r'https?://\S+')
    facets = []
    for match in url_pattern.finditer(content):
        url = match.group(0)
        start_idx = match.start()
        end_idx = match.end()
        byteStart = len(content[:start_idx].encode('utf-8'))
        byteEnd = len(content[:end_idx].encode('utf-8'))
        facets.append({
            "index": {
                "byteStart": byteStart,
                "byteEnd": byteEnd
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": url
                }
            ]
        })
    return facets

def extract_hashtag_facets(content):
    """Extract hashtag facets for Bluesky rich text."""
    hashtag_pattern = re.compile(r'#\w+')
    facets = []
    for match in hashtag_pattern.finditer(content):
        tag = match.group(0)[1:]  # Remove the '#' symbol
        start_idx = match.start()
        end_idx = match.end()
        byteStart = len(content[:start_idx].encode('utf-8'))
        byteEnd = len(content[:end_idx].encode('utf-8'))
        facets.append({
            "index": {
                "byteStart": byteStart,
                "byteEnd": byteEnd
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#tag",
                    "tag": tag
                }
            ]
        })
    return facets

def extract_first_url(content):
    """Extract the first URL from the content, or None if not found."""
    url_pattern = re.compile(r'https?://\S+')
    match = url_pattern.search(content)
    if match:
        return match.group(0)
    return None

def post_to_bluesky(content):
    """Post content to Bluesky with rich text formatting for URLs, hashtags, and link preview."""
    try:
        access_jwt = get_bluesky_auth()
        headers = {
            'Authorization': f'Bearer {access_jwt}',
            'Content-Type': 'application/json'
        }

        # Extract facets for URLs and hashtags
        url_facets = extract_url_facets(content)
        hashtag_facets = extract_hashtag_facets(content)
        all_facets = url_facets + hashtag_facets

        # Prepare post data
        post_data = {
            "$type": "app.bsky.feed.post",
            "text": content,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "langs": ["en"]
        }
        if all_facets:
            post_data["facets"] = all_facets

        # Add link preview (embed) for the first URL, if any
        main_url = extract_first_url(content)
        if main_url:
            post_data["embed"] = {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": main_url,
                    "title": main_url,  # Let Bluesky fill in the real preview
                    "description": ""   # Let Bluesky fill in the real preview
                }
            }

        resp = requests.post(
            'https://bsky.social/xrpc/com.atproto.repo.createRecord',
            headers=headers,
            json={
                "collection": "app.bsky.feed.post",
                "repo": BLUESKY_HANDLE,
                "record": post_data
            }
        )
        resp.raise_for_status()
        print("Post successful!")
        return True

    except requests.RequestException as e:
        print(f"Error posting to Bluesky: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        sys.exit(1)

def update_state(next_index):
    """Update state file with last posted index."""
    try:
        new_state = {
            'last_row_index': next_index,
            'last_post_time': datetime.now(timezone.utc).isoformat()
        }
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_state, f, indent=2)
        print(f"State updated: {new_state}")
    except Exception as e:
        print(f"Error updating state file: {str(e)}")
        sys.exit(1)

def commit_changes(next_index):
    """Commit state changes back to repository."""
    try:
        commit_message = f'Update state.json after posting row {next_index + 2}'
        # Configure Git
        os.system(f'git config user.name "{REPO_ACTOR}"')
        os.system(f'git config user.email "{REPO_ACTOR}@users.noreply.github.com"')
        # Add, commit and push changes
        os.system(f'git add {STATE_FILE}')
        os.system(f'git commit -m "{commit_message}"')
        if GITHUB_TOKEN:
            # If token is available, use it for authentication
            origin_url = f'https://x-access-token:{GITHUB_TOKEN}@github.com/{os.environ.get("GITHUB_REPOSITORY")}.git'
            os.system(f'git remote set-url origin {origin_url}')
        # Push changes
        os.system('git push')
        print("Changes committed and pushed successfully")
    except Exception as e:
        print(f"Error committing changes: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
