import re

def slugify(text: str) -> str:
    text = text.lower().strip()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ä","a"),("ë","e"),("ï","i"),("ö","o"),("ü","u"),("ñ","n")]:
        text = text.replace(a, b)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text).strip('-')
    return text

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

        jobs.append(Job(
            id=job_id,
            title=title,
            company=company,
            location=location,
            url=url,
            posted=posted,
            modality=modality,
            description=description,
        ))
    return jobs
