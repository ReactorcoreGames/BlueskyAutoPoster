import csv
import json
import os
import sys
import requests
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from io import BytesIO
from PIL import Image

# Constants
CSV_FILE = 'posts.csv'
STATE_FILE = 'state.json'
BLUESKY_HANDLE = os.environ.get('BLUESKY_HANDLE')
BLUESKY_APP_PASSWORD = os.environ.get('BLUESKY_APP_PASSWORD')
REPO_ACTOR = os.environ.get('GITHUB_ACTOR', 'github-actions[bot]')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

# Bluesky image size limit (in bytes) - leave some buffer
MAX_IMAGE_SIZE = 950 * 1024  # 950KB to be safe

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
        auth_data = resp.json()
        return auth_data['accessJwt'], auth_data['did']
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

def get_webpage_metadata(url):
    """Fetch webpage and extract metadata for link preview."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Initialize metadata with defaults
        metadata = {
            'title': soup.title.text.strip() if soup.title else url,
            'description': '',
            'image': None,
            'image_alt': ''
        }
        
        # Try to get OpenGraph metadata
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            metadata['title'] = og_title['content']
        
        og_description = soup.find('meta', property='og:description')
        if og_description and og_description.get('content'):
            metadata['description'] = og_description['content']
        
        # Try different image meta tags
        image_url = None
        
        # 1. OpenGraph image
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
            
            # Try to get image alt text
            og_image_alt = soup.find('meta', property='og:image:alt')
            if og_image_alt and og_image_alt.get('content'):
                metadata['image_alt'] = og_image_alt['content']
        
        # 2. Twitter image
        if not image_url:
            twitter_image = soup.find('meta', property='twitter:image')
            if twitter_image and twitter_image.get('content'):
                image_url = twitter_image['content']
                
                # Try to get image alt text
                twitter_image_alt = soup.find('meta', property='twitter:image:alt')
                if twitter_image_alt and twitter_image_alt.get('content'):
                    metadata['image_alt'] = twitter_image_alt['content']
        
        # 3. Regular image meta
        if not image_url:
            image_meta = soup.find('meta', attrs={'name': 'image'})
            if image_meta and image_meta.get('content'):
                image_url = image_meta['content']
        
        # 4. Look for the first large image
        if not image_url:
            for img in soup.find_all('img', src=True):
                # Skip small images, icons, etc.
                if img.get('width') and int(img['width']) < 100:
                    continue
                if img.get('height') and int(img['height']) < 100:
                    continue
                image_url = img['src']
                
                # Get alt text if available
                if img.get('alt'):
                    metadata['image_alt'] = img['alt']
                    
                break
        
        # Make sure image URL is absolute
        if image_url:
            metadata['image'] = urljoin(url, image_url)
        
        return metadata
        
    except Exception as e:
        print(f"Warning: Error fetching metadata for {url}: {str(e)}")
        return {
            'title': url,
            'description': '',
            'image': None,
            'image_alt': ''
        }

def resize_image_if_needed(image_data, max_size=MAX_IMAGE_SIZE, quality=85):
    """Resize image if it exceeds the maximum size limit."""
    try:
        original_size = len(image_data)
        print(f"Original image size: {original_size} bytes")
        
        if original_size <= max_size:
            print("Image is within size limit, no resizing needed")
            return image_data
        
        print(f"Image exceeds {max_size} bytes, resizing...")
        
        # Open image with PIL
        img = Image.open(BytesIO(image_data))
        original_format = img.format
        
        # Convert to RGB if necessary (for JPEG output)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create a white background for transparent images
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Try different strategies to reduce file size
        strategies = [
            # Strategy 1: Reduce quality
            {'resize_factor': 1.0, 'quality': 70},
            {'resize_factor': 1.0, 'quality': 60},
            {'resize_factor': 1.0, 'quality': 50},
            
            # Strategy 2: Resize image while maintaining quality
            {'resize_factor': 0.9, 'quality': 85},
            {'resize_factor': 0.8, 'quality': 85},
            {'resize_factor': 0.7, 'quality': 80},
            {'resize_factor': 0.6, 'quality': 80},
            {'resize_factor': 0.5, 'quality': 75},
            
            # Strategy 3: Aggressive resizing with lower quality
            {'resize_factor': 0.4, 'quality': 70},
            {'resize_factor': 0.3, 'quality': 65},
        ]
        
        for strategy in strategies:
            # Create a copy of the image for this attempt
            temp_img = img.copy()
            
            # Resize if needed
            if strategy['resize_factor'] < 1.0:
                new_width = int(temp_img.width * strategy['resize_factor'])
                new_height = int(temp_img.height * strategy['resize_factor'])
                temp_img = temp_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"Resized to {new_width}x{new_height} (factor: {strategy['resize_factor']})")
            
            # Save with specified quality
            output = BytesIO()
            temp_img.save(output, format='JPEG', quality=strategy['quality'], optimize=True)
            result_data = output.getvalue()
            result_size = len(result_data)
            
            print(f"Attempt with quality {strategy['quality']}, resize {strategy['resize_factor']}: {result_size} bytes")
            
            if result_size <= max_size:
                print(f"Successfully reduced image size from {original_size} to {result_size} bytes")
                return result_data
        
        # If all strategies failed, return the last attempt (smallest size)
        print(f"Warning: Could not reduce image below {max_size} bytes. Using smallest version ({result_size} bytes)")
        return result_data
        
    except Exception as e:
        print(f"Error resizing image: {str(e)}")
        # Return original data if resizing fails
        return image_data

def upload_image_blob(image_url, access_jwt):
    """Upload an image to Bluesky's XRPC service and return the blob reference."""
    try:
        print(f"Downloading image from: {image_url}")
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
        original_image_data = response.content
        original_content_type = response.headers.get('Content-Type', 'image/jpeg')
        
        print(f"Downloaded image (size: {len(original_image_data)} bytes, type: {original_content_type})")
        
        # Resize image if it's too large
        processed_image_data = resize_image_if_needed(original_image_data)
        
        # Always use JPEG for processed images to ensure compatibility
        content_type = 'image/jpeg'
        
        print(f"Uploading image as blob (final size: {len(processed_image_data)} bytes, type: {content_type})")
        
        headers = {
            'Authorization': f'Bearer {access_jwt}',
            'Content-Type': content_type
        }
        
        upload_response = requests.post(
            'https://bsky.social/xrpc/com.atproto.repo.uploadBlob',
            headers=headers,
            data=processed_image_data
        )
        upload_response.raise_for_status()
        
        blob_data = upload_response.json().get('blob')
        print(f"Image uploaded successfully as blob: {blob_data}")
        
        return blob_data
    except Exception as e:
        print(f"Error uploading image: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None

def post_to_bluesky(content):
    """Post content to Bluesky with rich text formatting for URLs, hashtags, and link preview."""
    try:
        access_jwt, did = get_bluesky_auth()
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
            # Get metadata including image from the URL
            print(f"Fetching metadata for {main_url}")
            metadata = get_webpage_metadata(main_url)
            
            external_embed = {
                "uri": main_url,
                "title": metadata['title'],
                "description": metadata['description']
            }
            
            # Add thumb if image was found - need to upload as blob first
            if metadata['image']:
                print(f"Found image for preview: {metadata['image']}")
                blob = upload_image_blob(metadata['image'], access_jwt)
                if blob:
                    external_embed["thumb"] = blob
                    if metadata['image_alt']:
                        external_embed["alt"] = metadata['image_alt']
            else:
                print("No image found for preview")
                
            post_data["embed"] = {
                "$type": "app.bsky.embed.external",
                "external": external_embed
            }

        resp = requests.post(
            'https://bsky.social/xrpc/com.atproto.repo.createRecord',
            headers=headers,
            json={
                "collection": "app.bsky.feed.post",
                "repo": did,
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