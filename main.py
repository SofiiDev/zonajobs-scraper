import httpx
import uuid
import re
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ZonaJobs Scraper API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

class Job(BaseModel):
    id: Optional[str] = None
    title: str
    company: str
    location: str
    url: str
    posted: Optional[str] = None
    salary: Optional[str] = None
    modality: Optional[str] = None
    description: Optional[str] = None

class SearchResult(BaseModel):
    query: str
    location: str
    total: int
    page: int
    jobs: list[Job]

def make_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.zonajobs.com.ar",
        "Referer": "https://www.zonajobs.com.ar/",
        "x-site-id": "ZJAR",
        "x-pre-session-token": str(uuid.uuid4()),
        "X-Channel": "ZJ",
        "X-Source": "WEB",
        "X-Country": "AR",
    }

def slugify(text: str) -> str:
    text = text.lower().strip()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),
                 ("ä","a"),("ë","e"),("ï","i"),("ö","o"),("ü","u"),("ñ","n")]:
        text = text.replace(a, b)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text).strip('-')
    return text

async def fetch_jobs(query: str, location: str, page: int, size: int) -> dict:
    params = {"pageSize": size, "page": page - 1, "sort": "RELEVANTES"}
    body = {"filtros": [], "query": query, "internacional": False}

    async with httpx.AsyncCl
