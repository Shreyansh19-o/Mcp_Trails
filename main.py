import os
import asyncio
os.environ["UVICORN_RELOAD"] = "False"  # Fix Windows multiprocessing

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse, parse_qs
import aiohttp  # ASYNC HTTP client
import re
import uvicorn
from typing import Optional, List
from typing import Tuple

app = FastAPI(
    title="YouTube Transcript MCP Server",
    description="ASYNC MCP-compliant endpoint for YouTube transcript extraction",
    version="2.1.0"
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
    """Extract video ID from YouTube URL (sync - pure parsing)."""
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

async def fetch_video_info(video_id: str) -> dict:
    """Async video metadata fetch."""
    async with aiohttp.ClientSession() as session:
        try:
            url = f"https://noembed.com/embed?url=https://youtube.com/watch?v={video_id}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except:
            pass
    return {}

async def fetch_transcript(video_id: str, lang: str = "en") -> Tuple[str, str]:
    """Fully async transcript extraction."""
    base_url = "https://www.youtube.com/api/timedtext"
    
    async with aiohttp.ClientSession() as session:
        # Try manual captions first
        params = {'v': video_id, 'lang': lang, 'format': 'json3'}
        try:
            async with session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200 and (await resp.text()).strip():
                    data = await resp.json()
                    text = ' '.join([event.get('text', '') for event in data.get('events', [])])
                    return re.sub(r'\s+', ' ', text).strip(), lang
        except:
            pass
        
        # Try auto-generated (asr)
        params = {'v': video_id, 'type': 'track', 'lang': lang, 'kind': 'asr', 'fmt': 'vtt'}
        try:
            async with session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    text = re.sub(r'<[^>]+>', '', text)
                    text = re.sub(r'\n+\d+:\d+:\d+\.\d+\s*-->\s*\d+:\d+:\d+\.\d+\s*\n', '', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return text, f"{lang}-asr"
        except:
            pass
    
    return "", ""

@app.post("/transcript", response_model=TranscriptResponse)
async def extract_transcript(request: TranscriptRequest):
    """🚀 ASYNC MCP: Extract transcript from YouTube video."""
    video_id = extract_video_id(request.url)
    
    if not video_id:
        raise HTTPException(400, "Invalid YouTube URL")
    
    # Run async tasks concurrently
    info_task = asyncio.create_task(fetch_video_info(video_id))
    transcript_task = asyncio.create_task(fetch_transcript(video_id, request.languages[0]))
    
    info, (transcript, detected_lang) = await asyncio.gather(info_task, transcript_task)
    
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
    return {"status": "healthy", "mcp": "youtube-transcript-async"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
