import os
import requests
from bs4 import BeautifulSoup
import html2text
import boto3
import shutil
from flask import Flask, render_template, request, jsonify
from botocore.client import Config
from botocore.exceptions import ClientError
from werkzeug.utils import secure_filename
from urllib.parse import urlparse, urljoin
import re
import tempfile
import logging
from collections import deque

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Cloudflare R2 configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else None

# Initialize S3 client for Cloudflare R2
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto'
    )
except Exception as e:
    logger.error(f"Failed to initialize R2 client: {str(e)}")
    s3_client = None

# Validate URL
def is_valid_url(url):
    pattern = r'^https?://[\w-]+(\.[\w-]+)+[/\w-]*$'
    return bool(re.match(pattern, url))

# Normalize URL to ensure consistency
def normalize_url(url, base_url):
    parsed_base = urlparse(base_url)
    absolute_url = urljoin(base_url, url.strip())
    parsed_absolute = urlparse(absolute_url)
    if parsed_absolute.netloc == parsed_base.netloc:
        return absolute_url
    return None

# Crawl website and extract HTML
def crawl_website(start_url, max_pages=100):
    visited = set()
    to_visit = deque([(start_url, 0)])
    html_pages = []
    base_domain = urlparse(start_url).netloc

    while to_visit and len(html_pages) < max_pages:
        url, depth = to_visit.popleft()
        if url in visited:
            continue

        visited.add(url)
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch {url}: HTTP {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            html_pages.append({"url": url, "html": response.text})

            # Extract links
            for link in soup.find_all('a', href=True):
                href = link['href']
                normalized_href = normalize_url(href, start_url)
                if normalized_href and normalized_href not in visited and len(visited) < max_pages:
                    to_visit.append((normalized_href, depth + 1))

            logger.info(f"Crawled {url} (Depth: {depth}, Total: {len(html_pages)})")
        except requests.RequestException as e:
            logger.error(f"Error crawling {url}: {str(e)}")
            continue

    return html_pages, None if html_pages else "No pages crawled successfully"

# Convert HTML to Markdown and save to temp files
def convert_to_markdown(html_pages, temp_dir):
    h = html2text.HTML2Text()
    h.body_width = 0  # Disable line wrapping
    markdown_files = []

    for page in html_pages:
        url = page['url']
        html_content = page['html']
        try:
            markdown = h.handle(html_content)
            filename = secure_filename(urlparse(url).path.lstrip('/') or 'index') + '.md'
            file_path = os.path.join(temp_dir, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(markdown)
            markdown_files.append({"url": url, "file_path": file_path, "filename": filename})
        except Exception as e:
            logger.error(f"Error converting {url} to Markdown: {str(e)}")
            continue

    return markdown_files, None if markdown_files else "No pages converted to Markdown"

# Upload Markdown files to R2
def upload_files_to_r2(markdown_files, bucket_name, temp_dir):
    if not s3_client:
        return None, "R2 client not initialized. Check credentials."
    
    uploaded_files = []
    try:
        for file_info in markdown_files:
            file_path = file_info['file_path']
            filename = file_info['filename']
            try:
                with open(file_path, 'rb') as file_data:
                    s3_client.upload_fileobj(
                        file_data,
                        bucket_name,
                        filename,
                        ExtraArgs={
                            "ACL": "public-read",
                            "ContentType": "text/markdown"
                        }
                    )
                uploaded_files.append(filename)
                logger.info(f"Uploaded {filename} to R2")
            except ClientError as e:
                return None, f"Failed to upload {filename}: {str(e)}"
    except Exception as e:
        return None, f"Error accessing files: {str(e)}"
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Deleted temporary directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Failed to delete temp directory {temp_dir}: {str(e)}")

    return uploaded_files, None if uploaded_files else "No files uploaded"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape_website():
    data = request.get_json()
    website_url = data.get('website_url', '').strip()
    max_pages = int(data.get('max_pages', 100))

    if not is_valid_url(website_url):
        return jsonify({"error": "Invalid URL. Must be in the format http(s)://domain.com", "stage": "validation"}), 400

    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Stage 1: Crawl website
        html_pages, error = crawl_website(website_url, max_pages)
        if error:
            return jsonify({"error": error, "stage": "crawl"}), 500

        # Stage 2: Convert HTML to Markdown
        markdown_files, error = convert_to_markdown(html_pages, temp_dir)
        if error:
            return jsonify({"error": error, "stage": "convert"}), 500

        # Stage 3: Upload files to R2
        uploaded_files, error = upload_files_to_r2(markdown_files, R2_BUCKET_NAME, temp_dir)
        if error:
            return jsonify({"error": error, "stage": "upload"}), 500

        return jsonify({
            "message": f"Successfully uploaded {len(uploaded_files)} Markdown files to Cloudflare R2",
            "files": uploaded_files,
            "stage": "complete"
        }), 200

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
