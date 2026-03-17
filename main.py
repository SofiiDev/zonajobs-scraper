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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

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
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        text = text.replace(a, b)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text).strip('-')
    return text

async def fetch_jobs(query: str, location: str, page: int, size: int) -> dict:
    params = {"pageSize": size, "page": page - 1, "sort": "RELEVANTES"}
    body = {"filtros": [], "query": query, "internacional": False}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        r = await client.post(
            "https://www.zonajobs.com.ar/api/avisos/searchV2",
            params=params,
            json=body,
            headers=make_headers(),
        )
        r.raise_for_status()
        return r.json()

def parse_jobs(raw: dict) -> list[Job]:
    jobs = []
    for item in raw.get("content", []):
        job_id = str(item.get("id", ""))
        title = item.get("titulo", "").strip()
        if not title:
            continue
        company = item.get("empresa", "Empresa confidencial")
        if item.get("confidencial"):
            company = "Empresa confidencial"
        location = item.get("localizacion", "Argentina")
        posted = item.get("fechaPublicacion")
        modality = item.get("modalidadTrabajo")
        description = item.get("detalle", "").strip() or None
        url = f"https://www.zonajobs.com.ar/empleos/detalle/{job_id}-{slugify(title)}.html"
        jobs.append(Job(id=job_id, title=title, company=company, location=location, url=url, posted=posted, modality=modality, description=description))
    return jobs

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>ZonaJobs API v3</h1><p><a href='/docs'>Docs</a> · <a href='/health'>Health</a> · <a href='/jobs?q=tecnico+seguridad+higiene'>Buscar</a></p>"

@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}

@app.get("/jobs", response_model=SearchResult)
async def search_jobs(
    q: str = Query(default="tecnico seguridad higiene"),
    l: str = Query(default=""),
    page: int = Query(default=1, ge=1, le=10),
    size: int = Query(default=20, ge=1, le=50),
):
    try:
        raw = await fetch_jobs(query=q, location=l, page=page, size=size)
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(503, "No se pudo conectar con ZonaJobs.")
    jobs = parse_jobs(raw)
    total = raw.get("total", len(jobs))
    return SearchResult(query=q, location=l or "Argentina", total=total, page=page, jobs=jobs)
