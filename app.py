import os
import zipfile
import requests
import boto3
import shutil
from flask import Flask, render_template, request, jsonify
from botocore.client import Config
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
import re
import tempfile
import logging

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
R2_ENDPOINT_URL = f"https://c633744eb31adb64ca1dc2ad9e89a645.r2.cloudflarestorage.com"

# Initialize S3 client for Cloudflare R2
s3_client = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

# Validate GitHub URL
def is_valid_github_url(url):
    pattern = r'^https://github\.com/[\w-]+/[\w-]+/?$'
    return bool(re.match(pattern, url))

# Extract owner and repo from GitHub URL
def parse_github_url(url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    if len(path_parts) >= 2:
        return path_parts[0], path_parts[1]
    return None, None

# Download and unzip GitHub repo
def download_and_unzip_repo(url, temp_dir):
    owner, repo = parse_github_url(url)
    if not owner or not repo:
        return None, "Invalid GitHub repository URL"

    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
    try:
        response = requests.get(zip_url, stream=True)
        if response.status_code != 200:
            return None, f"Failed to download repository: HTTP {response.status_code}"

        zip_path = os.path.join(temp_dir, 'repo.zip')
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Unzip the file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the extracted folder (usually <repo>-main)
        extracted_folder = os.path.join(temp_dir, f"{repo}-main")
        if not os.path.exists(extracted_folder):
            return None, "Extracted folder not found"
        
        # Explicitly remove zip file after extraction
        try:
            os.remove(zip_path)
            logger.info(f"Deleted temporary zip file: {zip_path}")
        except Exception as e:
            logger.error(f"Failed to delete zip file {zip_path}: {str(e)}")
        
        return extracted_folder, None
    except Exception as e:
        return None, f"Error downloading/unzipping repo: {str(e)}"

# Upload files to R2 and clean up
def upload_files_to_r2(folder_path, bucket_name, temp_dir):
    uploaded_files = []
    try:
        for root, _, files in os.walk(folder_path):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                # Create R2 key (relative path from extracted folder)
                relative_path = os.path.relpath(file_path, folder_path)
                r2_key = secure_filename(relative_path.replace(os.sep, '/'))
                
                try:
                    with open(file_path, 'rb') as file_data:
                        s3_client.upload_fileobj(
                            file_data,
                            bucket_name,
                            r2_key,
                            ExtraArgs={
                                "ACL": "public-read",
                                "ContentType": "application/octet-stream"
                            }
                        )
                    uploaded_files.append(r2_key)
                except Exception as e:
                    return None, f"Failed to upload {file_name}: {str(e)}"
        return uploaded_files, None
    except Exception as e:
        return None, f"Error accessing files: {str(e)}"
    finally:
        # Clean up extracted folder
        try:
            shutil.rmtree(folder_path, ignore_errors=True)
            logger.info(f"Deleted temporary folder: {folder_path}")
        except Exception as e:
            logger.error(f"Failed to delete folder {folder_path}: {str(e)}")
        # Verify temp_dir is empty
        try:
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Deleted empty temporary directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Failed to verify/delete temp directory {temp_dir}: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_repo():
    data = request.get_json()
    repo_url = data.get('repo_url', '').strip()

    if not is_valid_github_url(repo_url):
        return jsonify({"error": "Invalid GitHub URL. Must be in the format https://github.com/owner/repo"}), 400

    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download and unzip repo
        extracted_folder, error = download_and_unzip_repo(repo_url, temp_dir)
        if error:
            return jsonify({"error": error}), 500

        # Upload files to R2 and clean up
        uploaded_files, error = upload_files_to_r2(extracted_folder, R2_BUCKET_NAME, temp_dir)
        if error:
            return jsonify({"error": error}), 500

        return jsonify({
            "message": f"Successfully uploaded {len(uploaded_files)} files to Cloudflare R2",
            "files": uploaded_files
        }), 200

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
