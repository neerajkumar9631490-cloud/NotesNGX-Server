#!/usr/bin/env python3
"""
Notes NGX Backend Server
========================
Fetches PDF notes from a private GitHub repository and serves them via API.

REQUIRED SETUP:
---------------
1. Get GitHub Fine-Grained PAT from https://github.com/settings/tokens?type=beta
   - Repository access: Select your private repo
   - Permissions: Contents → Read-only

2. Fill in the 4 CONFIG values below.

3. Repo folder structure MUST be:
   your-repo/
   ├── physics/
   │   └── (PDF files here)
   ├── chemistry/
   │   └── (PDF files here)
   └── mathematics/
       └── (PDF files here)

4. pip install flask flask-cors requests
5. python server.py
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — FILL THESE IN WITH YOUR VALUES
# ═══════════════════════════════════════════════════════════════════════════════

GITHUB_TOKEN  = "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"  # ← PASTE YOUR FULL github_pat_ TOKEN
GITHUB_OWNER  = "neerajkumar9631490-cloud"                  # ← YOUR GITHUB USERNAME
GITHUB_REPO   = "NotesNGX-Server"                           # ← YOUR PRIVATE REPO NAME (exact from URL)
GITHUB_BRANCH = "main"                                       # ← branch name (main or master)

# ═══════════════════════════════════════════════════════════════════════════════
# SERVER CODE — DON'T EDIT BELOW UNLESS YOU KNOW WHAT YOU'RE DOING
# ═══════════════════════════════════════════════════════════════════════════════

import os
import requests
from urllib.parse import quote
from flask import Flask, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_BASE = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"

# Detect token type and set correct auth header format
# github_pat_xxx tokens use "token" prefix, ghp_xxx tokens use "Bearer" prefix
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
        return {"error": "Invalid GitHub token. Check your GITHUB_TOKEN.", "status": 401}, 401
    if resp.status_code == 404:
        return {"error": f"Not found: {path}. Check owner/repo/branch/folder names.", "status": 404}, 404
    if resp.status_code == 403:
        return {"error": "GitHub API rate limit hit or token lacks permissions.", "status": 403}, 403
    resp.raise_for_status()
    return resp.json(), 200


@app.route("/api/notes/<subject>")
def list_notes(subject):
    """
    List all PDF files in a subject folder from GitHub.
    Returns JSON with files array. If folder doesn't exist or is empty, returns empty files array.
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
        # Folder doesn't exist → return empty with message
        return jsonify({
            "subject": subject,
            "count": 0,
            "files": [],
            "message": "No folder found. Notes coming soon!"
        }), 200

    if status != 200:
        return jsonify(data), status

    # data is a list of items in the folder
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


@app.route("/api/download/<subject>/<path:filename>")
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


@app.route("/api/health")
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
            "default_branch": repo_data.get("default_branch")
        })
    else:
        return jsonify({
            "status": "error",
            "github_connected": False,
            "message": f"GitHub API returned {resp.status_code}: {resp.text[:200]}"
        }), 500


@app.route("/")
def index():
    """Root endpoint with API documentation."""
    return jsonify({
        "service": "Notes NGX API",
        "endpoints": {
            "GET /api/health": "Check server + GitHub connection",
            "GET /api/notes/<subject>": "List PDFs (physics/chemistry/mathematics)",
            "GET /api/download/<subject>/<filename>": "Download a PDF file"
        },
        "example_calls": [
            "http://localhost:5000/api/notes/physics",
            "http://localhost:5000/api/download/physics/Kinematics.pdf"
        ]
    })


if __name__ == "__main__":
    if "YOUR_TOKEN" in GITHUB_TOKEN or not GITHUB_TOKEN or len(GITHUB_TOKEN) < 20:
        print("\n" + "="*60)
        print("❌ ERROR: You must set your GITHUB_TOKEN in server.py!")
        print("="*60)
        print("Get your token from: https://github.com/settings/tokens?type=beta")
        exit(1)

    if GITHUB_OWNER == "neerajkumar9631490-cloud":
        print("\n⚠️  WARNING: Using default owner. Make sure this is YOUR username!")

    if GITHUB_REPO == "NotesNGX-Server":
        print("\n⚠️  WARNING: Using default repo name. Make sure this matches YOUR repo!")

    print("\n" + "="*60)
    print("🚀 Notes NGX Server Starting...")
    print("="*60)
    print(f"   GitHub: {GITHUB_OWNER}/{GITHUB_REPO} ({GITHUB_BRANCH})")
    print(f"   Token:  {GITHUB_TOKEN[:20]}... ({'Fine-Grained PAT' if GITHUB_TOKEN.startswith('github_pat_') else 'Classic PAT'})")
    print("="*60)
    print("   http://localhost:5000/api/health")
    print("   http://localhost:5000/api/notes/physics")
    print("   http://localhost:5000/api/download/physics/filename.pdf")
    print("="*60 + "\n")

    app.run(host="0.0.0.0", port=5000, debug=True)
