"""Utilidades compartidas: sesión HTTP, normalización de texto y avisos."""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.6",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        }
    )
    return s


def obtener(s: requests.Session, url: str, **kw) -> requests.Response:
    """GET con una pausa corta y un reintento ante errores transitorios."""
    for intento in range(2):
        time.sleep(random.uniform(1.0, 2.5))
        try:
            r = s.get(url, timeout=25, **kw)
        except requests.RequestException:
            if intento:
                raise
            continue
        if r.status_code in (429, 500, 502, 503, 504) and not intento:
            time.sleep(5)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"sin respuesta de {url}")


def normalizar(txt: str | None) -> str:
    """Minúsculas y sin tildes, para comparar textos."""
    if not txt:
        return ""
    t = unicodedata.normalize("NFKD", txt)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def limpio(txt: str | None) -> str:
    return re.sub(r"\s+", " ", txt or "").strip()


def url_canonica(url: str) -> str:
    """Quita parámetros de seguimiento para que el mismo aviso tenga una sola URL."""
    p = urlsplit(url)
    return urlunsplit((p.scheme or "https", p.netloc.lower(), p.path.rstrip("/"), "", ""))


@dataclass
class Aviso:
    sitio: str
    titulo: str
    url: str
    empresa: str = ""
    ubicacion: str = ""
    publicado: str = ""
    palabras: list[str] = field(default_factory=list)
    # Detalle opcional, cuando el sitio lo muestra en el listado
    renta: str = ""
    jornada: str = ""
    contrato: str = ""
    cierre: str = ""  # fecha límite de postulación (AAAA-MM-DD)

    def completar_desde_texto(self, texto: str) -> "Aviso":
        """Rellena renta, jornada y contrato a partir de texto libre (título, tarjeta)."""
        d = detalle_desde_texto(f"{self.titulo} {texto}")
        for k, v in d.items():
            if v and not getattr(self, k):
                setattr(self, k, v)
        return self

    @property
    def id(self) -> str:
        return hashlib.sha1(url_canonica(self.url).encode()).hexdigest()[:14]


_JORNADAS = [
    (r"\bpart[\s-]?time\b|media jornada|jornada parcial", "Part time"),
    (r"\bfull[\s-]?time\b|jornada completa", "Jornada completa"),
    (r"\b\d{1,2}\s?x\s?\d{1,2}\b", None),  # turnos 7x7, 4x3: se usa el texto tal cual
    (r"\bturnos?\b", "Turnos"),
    (r"\bfin(es)? de semana\b", "Fin de semana"),
]
_CONTRATOS = [
    (r"\breemplazos?\b", "Reemplazo"),
    (r"\bindefinido\b", "Indefinido"),
    (r"\bplazo fijo\b", "Plazo fijo"),
    (r"\bhonorarios\b", "Honorarios"),
    (r"\bcontrata\b", "Contrata"),
    (r"\bplanta\b", "Planta"),
]


def detalle_desde_texto(texto: str) -> dict:
    t = normalizar(texto)
    out = {"renta": "", "jornada": "", "contrato": ""}
    m = re.search(r"\$\s?\d{1,3}(?:[.\s]\d{3})+(?:\s?(?:a|-)\s?\$?\s?\d{1,3}(?:[.\s]\d{3})+)?", texto or "")
    if m:
        out["renta"] = limpio(m.group(0))
    for rx, nombre in _JORNADAS:
        mm = re.search(rx, t)
        if mm:
            out["jornada"] = nombre or "Turno " + mm.group(0).replace(" ", "")
            break
    for rx, nombre in _CONTRATOS:
        if re.search(rx, t):
            out["contrato"] = nombre
            break
    return out


def json_ld_ofertas(html: str) -> list[dict]:
    """Extrae objetos JobPosting de bloques JSON-LD, si la página los trae."""
    out: list[dict] = []
    for bloque in re.findall(
        r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, flags=re.S | re.I
    ):
        try:
            data = json.loads(bloque.strip())
        except ValueError:
            continue
        pila = [data]
        while pila:
            x = pila.pop()
            if isinstance(x, list):
                pila.extend(x)
            elif isinstance(x, dict):
                if x.get("@type") == "JobPosting":
                    out.append(x)
                pila.extend(v for v in x.values() if isinstance(v, (list, dict)))
    return out
