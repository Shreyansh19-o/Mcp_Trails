# Add this at top of main.py
import os
os.environ["UVICORN_RELOAD"] = "False"  # Fix Windows multiprocessing

from fastapi import FastAPI, HTTPException
# ... rest of your code unchanged ...

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse, parse_qs
import requests
import re
import uvicorn
from typing import Optional, List

app = FastAPI(
    title="YouTube Transcript MCP Server",
    description="MCP-compliant endpoint for YouTube transcript extraction",
    version="2.0.0"
)

class TranscriptRequest(BaseModel):
    url: str
    languages: Optional[List[str]] = ["en"]

class TranscriptResponse(BaseModel):
    success: bool
    video_id: str
    title: Optional[str] = None
    duration: Optional[int] = None
    transcript: str = ""
    language: str = ""
    error: Optional[str] = None

def extract_video_id(url: str) -> str:
    """Extract video ID from YouTube URL."""
    parsed = urlparse(url)
    hostnames = ('youtu.be', 'www.youtube.com', 'youtube.com', 'm.youtube.com')
    if parsed.hostname in hostnames:
        if parsed.path.startswith('/shorts/'):
            return parsed.path.split('/')[-1]
        if parsed.hostname == 'youtu.be':
            return parsed.path.split('/')[-1]
    if parsed.query:
        params = parse_qs(parsed.query)
        return params.get('v', [''])[0]
    return ""

def fetch_video_info(video_id: str) -> dict:
    """Get basic video metadata."""
    try:
        url = f"https://noembed.com/embed?url=https://youtube.com/watch?v={video_id}"
        resp = requests.get(url, timeout=10)
        return resp.json() if resp.status_code == 200 else {}
    except:
        return {}

def fetch_transcript(video_id: str, lang: str = "en") -> tuple[str, str]:
    """Fetch transcript text and detect language."""
    base_url = "https://www.youtube.com/api/timedtext"
    
    # Try manual captions first
    params = {'v': video_id, 'lang': lang, 'format': 'json3'}
    try:
        resp = requests.get(base_url, params=params, timeout=15)
        if resp.status_code == 200 and resp.text.strip():
            data = resp.json()
            text = ' '.join([event.get('text', '') for event in data.get('events', [])])
            return re.sub(r'\s+', ' ', text).strip(), lang
    except:
        pass
    
    # Try auto-generated (asr)
    params = {'v': video_id, 'type': 'track', 'lang': lang, 'kind': 'asr', 'fmt': 'vtt'}
    try:
        resp = requests.get(base_url, params=params, timeout=15)
        if resp.status_code == 200:
            text = re.sub(r'<[^>]+>', '', resp.text)
            text = re.sub(r'\n+\d+:\d+:\d+\.\d+\s*-->\s*\d+:\d+:\d+\.\d+\s*\n', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text, f"{lang}-asr"
    except:
        pass
    
    return "", ""

@app.post("/transcript", response_model=TranscriptResponse)
async def extract_transcript(request: TranscriptRequest):
    """MCP: Extract transcript from YouTube video."""
    video_id = extract_video_id(request.url)
    
    if not video_id:
        raise HTTPException(400, "Invalid YouTube URL")
    
    info = fetch_video_info(video_id)
    transcript, detected_lang = fetch_transcript(video_id, request.languages[0])
    
    if not transcript:
        raise HTTPException(404, "No captions available")
    
    return TranscriptResponse(
        success=True,
        video_id=video_id,
        title=info.get('title'),
        duration=info.get('duration'),
        transcript=transcript[:15000],
        language=detected_lang
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "mcp": "youtube-transcript"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
