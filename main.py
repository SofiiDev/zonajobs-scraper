"""
ZonaJobs Scraper — FastAPI
Estrategia: llamada directa a la API interna REST de Navent (grupo ZonaJobs/Bumeran)
Sin browser headless, sin parseo HTML. Respuesta JSON limpia y rápida.

Correr local:
    pip install -r requirements.txt
    uvicorn main:app --reload

Deploy (Railway / Render):
    Variable de entorno PORT se detecta automáticamente.
"""

import httpx
import asyncio
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ZonaJobs Scraper API",
    description="Consulta empleos de ZonaJobs via su API interna REST.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Configuración de la API interna de Navent
# ---------------------------------------------------------------------------

BASE_URL = "https://api.zonajobs.com.ar"
BUMERAN_URL = "https://api.bumeran.com"

# Headers que imitan las llamadas XHR reales del navegador en ZonaJobs
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9",
    "Origin": "https://www.zonajobs.com.ar",
    "Referer": "https://www.zonajobs.com.ar/",
    "X-Channel": "ZJ",
    "X-Source": "WEB",
}

BUMERAN_HEADERS = {
    **API_HEADERS,
    "X-Channel": "BM",
    "Referer": "https://www.bumeran.com.ar/",
    "Origin": "https://www.bumeran.com.ar",
}


# ---------------------------------------------------------------------------
# Fetch con múltiples endpoints fallback
# ---------------------------------------------------------------------------

ENDPOINTS = [
    # (url_base, params_extra, headers)
    (f"{BASE_URL}/job-search/jobs",   {"canal": "ZJ"}, API_HEADERS),
    (f"{BASE_URL}/search/avisos",     {"canal": "ZJ"}, API_HEADERS),
    (f"{BUMERAN_URL}/job-search/jobs", {"canal": "BM"}, BUMERAN_HEADERS),
]


async def fetch_jobs(query: str, location: str, page: int, size: int) -> dict:
    params_base = {"q": query, "pg": page, "psize": size}
    if location:
        params_base["l"] = location

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        for url, extra_params, headers in ENDPOINTS:
            params = {**params_base, **extra_params}
            try:
                logger.info(f"→ GET {url} {params}")
                r = await client.get(url, params=params, headers=headers)
                r.raise_for_status()
                data = r.json()
                if data:
                    logger.info(f"✓ Respuesta de {url}")
                    return data
            except Exception as e:
                logger.warning(f"✗ {url}: {e}")

    return {}


# ---------------------------------------------------------------------------
# Parseo de respuesta Navent
# ---------------------------------------------------------------------------

def extract_jobs_list(raw: dict) -> list:
    """Extrae la lista de avisos del JSON de la API (estructura variable por versión)."""
    if isinstance(raw, list):
        return raw
    for key in ("avisos", "postings", "jobs", "results", "data"):
        val = raw.get(key)
        if isinstance(val, list) and val:
            return val
        if isinstance(val, dict):
            for sub in ("avisos", "postings", "jobs", "results"):
                if isinstance(val.get(sub), list):
                    return val[sub]
    return []


def parse_job(item: dict) -> Optional[Job]:
    if not item:
        return None

    job_id = str(item.get("id") or item.get("avisoId") or item.get("postingId") or "")

    title = (item.get("titulo") or item.get("title") or item.get("postingTitle") or "").strip()
    if not title:
        return None

    # Empresa
    co = item.get("empresa") or item.get("company") or {}
    company = (co.get("nombre") or co.get("name") or str(co) if isinstance(co, dict) else str(co)) or "Empresa confidencial"

    # Ubicación
    loc = item.get("ubicacion") or item.get("location") or {}
    if isinstance(loc, dict):
        city = loc.get("ciudad") or loc.get("city") or ""
        province = loc.get("provincia") or loc.get("state") or ""
        location = ", ".join(filter(None, [city, province])) or "Argentina"
    else:
        location = str(loc) or "Argentina"

    # URL
    slug = item.get("slug") or item.get("url") or ""
    if slug and slug.startswith("http"):
        url = slug
    elif slug:
        url = f"https://www.zonajobs.com.ar/empleos/detalle/{slug}"
    elif job_id:
        url = f"https://www.zonajobs.com.ar/empleos/detalle/{job_id}"
    else:
        url = "https://www.zonajobs.com.ar"

    # Salario
    sal = item.get("salario") or item.get("salary") or {}
    salary = None
    if isinstance(sal, dict):
        mn = sal.get("minimo") or sal.get("min")
        mx = sal.get("maximo") or sal.get("max")
        currency = sal.get("moneda") or "$"
        if mn and mx:
            salary = f"{currency} {int(mn):,} - {int(mx):,}".replace(",", ".")
        elif mn:
            salary = f"{currency} {int(mn):,}+".replace(",", ".")

    # Fecha
    posted_raw = item.get("fechaPublicacion") or item.get("publishedAt") or item.get("date")
    posted = str(posted_raw)[:10] if posted_raw else None

    # Descripción
    desc = (item.get("descripcionBreve") or item.get("description") or item.get("resumen") or "")
    description = str(desc)[:200].strip() or None

    # Modalidad
    mod_raw = str(item.get("modalidad") or item.get("modality") or item.get("workMode") or "").lower()
    modality = {
        "remoto": "Remoto", "remote": "Remoto",
        "hibrido": "Híbrido", "hybrid": "Híbrido", "híbrido": "Híbrido",
        "presencial": "Presencial", "on-site": "Presencial",
    }.get(mod_raw)

    return Job(
        id=job_id or None,
        title=title,
        company=company,
        location=location,
        url=url,
        posted=posted,
        salary=salary,
        modality=modality,
        description=description,
    )


def parse_response(raw: dict) -> tuple[list[Job], int]:
    items = extract_jobs_list(raw)
    jobs = [j for item in items if (j := parse_job(item))]
    total = int(
        raw.get("total") or raw.get("totalResultados") or
        raw.get("totalCount") or len(jobs)
    )
    return jobs, total


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>ZonaJobs API</title>
<style>
  body{font-family:monospace;padding:2rem;max-width:680px;margin:auto;color:#1a1a1a}
  h1{font-size:1.5rem}
  .tag{background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:4px;font-size:.8rem}
  .box{background:#f8f8f8;border:1px solid #e0e0e0;padding:1rem;border-radius:6px;margin:.75rem 0}
  code{background:#ececec;padding:1px 5px;border-radius:3px}
  a{color:#1d4ed8}
</style></head><body>
<h1>ZonaJobs Scraper <span class="tag">v2.0</span></h1>
<p>API REST que consulta empleos en tiempo real desde ZonaJobs.</p>
<div class="box"><b>GET /jobs</b> — Buscar empleos<br>
<code>GET /jobs?q=tecnico+seguridad+higiene&amp;l=Buenos+Aires</code></div>
<div class="box"><b>GET /jobs/{id}</b> — Detalle de aviso<br>
<code>GET /jobs/12345678</code></div>
<p>
  <a href="/docs">Swagger UI</a> ·
  <a href="/health">Health</a> ·
  <a href="/jobs?q=tecnico+seguridad+higiene&l=Buenos+Aires">Ejemplo búsqueda</a>
</p>
</body></html>"""


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/jobs", response_model=SearchResult)
async def search_jobs(
    q: str = Query(default="tecnico seguridad higiene", description="Puesto a buscar"),
    l: str = Query(default="", description="Ubicación (ej: Buenos Aires, Córdoba)"),
    page: int = Query(default=1, ge=1, le=10),
    size: int = Query(default=20, ge=1, le=50),
):
    """Busca empleos en ZonaJobs via su API interna."""
    raw = await fetch_jobs(query=q, location=l, page=page, size=size)
    if not raw:
        raise HTTPException(503, "No se pudo conectar con ZonaJobs. Reintentá en unos segundos.")

    jobs, total = parse_response(raw)
    return SearchResult(query=q, location=l or "Argentina", total=total, page=page, jobs=jobs)


@app.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str):
    """Detalle de un aviso por su ID."""
    async with httpx.AsyncClient(headers=API_HEADERS, timeout=15.0) as client:
        try:
            r = await client.get(f"{BASE_URL}/job-search/jobs/{job_id}")
            r.raise_for_status()
            job = parse_job(r.json())
            if not job:
                raise HTTPException(404, "Aviso no encontrado")
            return job
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(404, f"Aviso no encontrado: {job_id}")
