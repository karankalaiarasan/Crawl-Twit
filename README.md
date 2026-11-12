# Crawl

Crawl is a Twitter/X-style social app built with FastAPI, Jinja2, MongoDB Atlas, Firebase Authentication, and Azure Blob Storage via Azurite.

## Features
- Post and repost content
- Edit and delete your own posts
- Profile pages and user bios
- Follow and unfollow users
- Image uploads for posts
- Search for users and content

## Setup
1. Create and activate a Python virtual environment.
2. Copy `.env.example` to `.env` and replace the sample MongoDB URI with your real Atlas connection string.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start Azurite locally if you want to test image uploads:
   ```bash
   azurite --silent --blobHost 127.0.0.1 --blobPort 10000 --location .
   ```

## Run
```bash
uvicorn A2-3115004.main:app --reload
```

Open the app in your browser at `http://127.0.0.1:8000`.

## Notes
- Keep `.env` local and do not commit real credentials.
- The repository intentionally ignores local environment files, temporary Python cache files, Azurite data, and editor settings.
