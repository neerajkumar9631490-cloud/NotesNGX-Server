#!/usr/bin/env python3
"""
Notes NGX Backend Server
Serves HTML pages AND provides API for PDF notes
Includes built-in keep-alive to prevent Render from sleeping
"""

import os
import time
import threading
import requests
from urllib.parse import quote
from flask import Flask, jsonify, Response, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.')
CORS(app)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — From environment variables (set in Render dashboard)
# ═══════════════════════════════════════════════════════════════════════════════

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "neerajkumar9631490-cloud")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "NotesNGX-Server")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
RENDER_URL = os.environ.get("RENDER_URL", "http://localhost:5000")

# ═══════════════════════════════════════════════════════════════════════════════
# GITHUB API FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

API_BASE = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"

if GITHUB_TOKEN.startswith("github_pat_"):
    AUTH_HEADER = f"token {GITHUB_TOKEN}"
else:
    AUTH_HEADER = f"Bearer {GITHUB_TOKEN}"

HEADERS = {
    "Authorization": AUTH_HEADER,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10"
}

def github_api_get(path):
    """Make authenticated GET request to GitHub API."""
    url = f"{API_BASE}{path}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 401:
        return {"error": "Invalid GitHub token.", "status": 401}, 401
    if resp.status_code == 404:
        return {"error": f"Not found: {path}", "status": 404}, 404
    if resp.status_code == 403:
        return {"error": "GitHub API rate limit hit or token lacks permissions.", "status": 403}, 403
    resp.raise_for_status()
    return resp.json(), 200

# ═══════════════════════════════════════════════════════════════════════════════
# SERVE STATIC HTML PAGES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Serve the main index.html page"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve all static files (HTML, CSS, images)"""
    # Skip API routes
    if path.startswith('api/'):
        return jsonify({"error": "Not found"}), 404
    
    # Serve static files
    try:
        return send_from_directory('.', path)
    except:
        return jsonify({"error": "File not found"}), 404

# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/notes/<subject>')
def list_notes(subject):
    """
    List all PDF files in a subject folder from GitHub.
    Returns JSON with files array.
    """
    subject = subject.lower().strip()
    valid_subjects = {"physics", "chemistry", "mathematics"}

    if subject not in valid_subjects:
        return jsonify({
            "error": f"Invalid subject '{subject}'. Must be one of: {', '.join(valid_subjects)}"
        }), 400

    path = f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{subject}?ref={GITHUB_BRANCH}"
    data, status = github_api_get(path)

    if status == 404:
        return jsonify({
            "subject": subject,
            "count": 0,
            "files": [],
            "message": "No folder found. Notes coming soon!"
        }), 200

    if status != 200:
        return jsonify(data), status

    files = []
    for item in data:
        if item.get("type") == "file" and item.get("name", "").lower().endswith(".pdf"):
            files.append({
                "name": item["name"],
                "size": item.get("size", 0),
                "path": item.get("path", ""),
                "download_url": item.get("download_url", "")
            })

    files.sort(key=lambda x: x["name"])

    return jsonify({
        "subject": subject,
        "count": len(files),
        "files": files,
        "message": "Notes loaded successfully" if files else "No PDFs found. Notes coming soon!"
    })

@app.route('/api/download/<subject>/<path:filename>')
def download_note(subject, filename):
    """
    Download/serve a specific PDF file from GitHub.
    Proxies through server to avoid CORS and hide token.
    """
    subject = subject.lower().strip()
    valid_subjects = {"physics", "chemistry", "mathematics"}

    if subject not in valid_subjects:
        return jsonify({"error": f"Invalid subject '{subject}'"}), 400

    encoded_filename = quote(filename)
    raw_url = f"{RAW_BASE}/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{subject}/{encoded_filename}"

    resp = requests.get(raw_url, headers=HEADERS, timeout=60, stream=True)

    if resp.status_code == 404:
        return jsonify({"error": f"File not found: {subject}/{filename}"}), 404
    if resp.status_code == 401:
        return jsonify({"error": "Invalid GitHub token"}), 401

    resp.raise_for_status()

    return Response(
        resp.iter_content(chunk_size=8192),
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )

@app.route('/api/health')
def health():
    """Health check + verify GitHub token works."""
    url = f"{API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
    resp = requests.get(url, headers=HEADERS, timeout=10)

    if resp.status_code == 200:
        repo_data = resp.json()
        return jsonify({
            "status": "ok",
            "github_connected": True,
            "repo": repo_data.get("full_name"),
            "private": repo_data.get("private"),
            "default_branch": repo_data.get("default_branch"),
            "server": "running",
            "keep_alive": "active"
        })
    else:
        return jsonify({
            "status": "error",
            "github_connected": False,
            "message": f"GitHub API returned {resp.status_code}"
        }), 500

@app.route('/api/info')
def info():
    """Get server information"""
    return jsonify({
        "service": "Notes NGX API",
        "version": "1.0.0",
        "endpoints": {
            "/": "Main page (index.html)",
            "/<page>": "Serve static pages (about, support, etc.)",
            "/api/health": "Check server + GitHub connection",
            "/api/info": "Server information",
            "/api/notes/<subject>": "List PDFs (physics/chemistry/mathematics)",
            "/api/download/<subject>/<filename>": "Download a PDF file"
        },
        "subjects": ["physics", "chemistry", "mathematics"],
        "keep_alive": {
            "status": "active",
            "interval": "10 minutes",
            "target": RENDER_URL
        }
    })

# ═══════════════════════════════════════════════════════════════════════════════
# KEEP-ALIVE FUNCTION (Prevents Render from sleeping)
# ═══════════════════════════════════════════════════════════════════════════════

def keep_alive():
    """
    Keep the server alive by pinging itself every 10 minutes.
    Prevents Render from putting the server to sleep after 15 minutes of inactivity.
    """
    # Wait 5 minutes before starting (give server time to fully start)
    time.sleep(300)
    
    # Use the Render URL or localhost
    url = RENDER_URL if "render.com" in RENDER_URL else "https://notes-ngx-server.onrender.com"
    
    # Remove trailing slash
    if url.endswith('/'):
        url = url[:-1]
    
    health_url = f"{url}/api/health"
    
    print(f"🔄 Keep-alive started! Pinging {health_url} every 10 minutes...")
    
    while True:
        try:
            response = requests.get(health_url, timeout=10)
            if response.status_code == 200:
                print(f"✅ Keep-alive ping successful at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print(f"⚠️ Keep-alive ping returned status: {response.status_code}")
        except Exception as e:
            print(f"❌ Keep-alive ping failed: {str(e)}")
        
        # Wait 10 minutes (600 seconds)
        time.sleep(600)

def start_keep_alive():
    """Start keep-alive in a separate thread so it doesn't block the server"""
    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()
    print("✅ Keep-alive thread started!")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN - START THE SERVER
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Check if GitHub token is set
    if not GITHUB_TOKEN or len(GITHUB_TOKEN) < 20:
        print("\n" + "="*60)
        print("❌ ERROR: You must set your GITHUB_TOKEN environment variable!")
        print("="*60)
        print("Get your token from: https://github.com/settings/tokens?type=beta")
        print("Then set it in Render dashboard under Environment Variables")
        print("="*60 + "\n")
        exit(1)

    print("\n" + "="*60)
    print("🚀 Notes NGX Server Starting...")
    print("="*60)
    print(f"   GitHub: {GITHUB_OWNER}/{GITHUB_REPO} ({GITHUB_BRANCH})")
    print(f"   Token:  {GITHUB_TOKEN[:20]}...")
    print(f"   Render URL: {RENDER_URL}")
    print("="*60)
    print("   http://localhost:5000/")
    print("   http://localhost:5000/api/health")
    print("   http://localhost:5000/api/notes/physics")
    print("   http://localhost:5000/api/info")
    print("="*60)
    print("🔄 Keep-alive will ping every 10 minutes to prevent sleeping")
    print("="*60 + "\n")

    # Start the keep-alive thread
    start_keep_alive()

    # Start the Flask server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
