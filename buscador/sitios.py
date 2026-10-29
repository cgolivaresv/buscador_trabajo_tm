"""Un lector por portal. Cada función recibe una palabra clave y devuelve avisos.

Los portales cambian su HTML de vez en cuando. Cada lector prueba primero la
estructura conocida y, si no encuentra nada, cae a una lectura genérica de los
enlaces a avisos, para seguir funcionando aunque cambie el diseño.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote, quote_plus, urljoin

from bs4 import BeautifulSoup

from .comun import Aviso, json_ld_ofertas, limpio, normalizar, obtener


def _enlaces_genericos(sitio: str, html: str, base: str, patron: str) -> list[Aviso]:
    """Respaldo: toma enlaces cuya URL parece de un aviso individual."""
    soup = BeautifulSoup(html, "html.parser")
    vistos: set[str] = set()
    out: list[Aviso] = []
    rx = re.compile(patron)
    for a in soup.find_all("a", href=True):
        url = urljoin(base, a["href"])
        titulo = limpio(a.get_text(" "))
        if not rx.search(url) or len(titulo) < 6 or url in vistos:
            continue
        vistos.add(url)
        out.append(Aviso(sitio=sitio, titulo=titulo, url=url))
    return out


def _desde_json_ld(sitio: str, html: str, base: str) -> list[Aviso]:
    out = []
    for o in json_ld_ofertas(html):
        url = o.get("url") or o.get("@id")
        if not url or not o.get("title"):
            continue
        org = o.get("hiringOrganization") or {}
        loc = o.get("jobLocation") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        addr = loc.get("address") or {} if isinstance(loc, dict) else {}
        ubic = ", ".join(
            x for x in (addr.get("addressLocality"), addr.get("addressRegion")) if isinstance(x, str) and x
        )
        out.append(
            Aviso(
                sitio=sitio,
                titulo=limpio(o["title"]),
                url=urljoin(base, url),
                empresa=limpio(org.get("name") if isinstance(org, dict) else ""),
                ubicacion=ubic,
                publicado=str(o.get("datePosted") or ""),
            )
        )
    return out


# --------------------------------------------------------------------------- LinkedIn
def linkedin(s, palabra: str) -> list[Aviso]:
    """Búsqueda pública de empleos (sin iniciar sesión), últimos 7 días, en Chile."""
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={quote_plus(palabra)}&location=Chile&f_TPR=r604800&start=0"
    )
    html = obtener(s, url).text
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select("li"):
        a = li.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        t = li.select_one(".base-search-card__title")
        if not a or not t:
            continue
        emp = li.select_one(".base-search-card__subtitle")
        loc = li.select_one(".job-search-card__location")
        fecha = li.select_one("time")
        out.append(
            Aviso(
                sitio="linkedin",
                titulo=limpio(t.get_text(" ")),
                url=a["href"].split("?")[0],
                empresa=limpio(emp.get_text(" ") if emp else ""),
                ubicacion=limpio(loc.get_text(" ") if loc else ""),
                publicado=(fecha.get("datetime") or "") if fecha else "",
            )
        )
    return out


# ----------------------------------------------------------------------- Computrabajo
def computrabajo(s, palabra: str) -> list[Aviso]:
    base = "https://cl.computrabajo.com"
    url = f"{base}/ofertas-de-trabajo/?q={quote_plus(palabra)}"
    html = obtener(s, url).text
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.select("article.box_offer, article[data-id]"):
        a = art.select_one("h2 a, a.js-o-link")
        if not a or not a.get("href"):
            continue
        ps = art.select("p")
        empresa = ""
        ubic = ""
        emp_a = art.select_one("p a[offer-grid-article-company-url], p.dIB a, p a.fc_base")
        if emp_a:
            empresa = limpio(emp_a.get_text(" "))
        span = art.select_one("p span.mr10")
        if span:
            ubic = limpio(span.get_text(" "))
        elif len(ps) > 1:
            ubic = limpio(ps[1].get_text(" "))
        fecha = art.select_one("p.fs13, p.fc_aux")
        out.append(
            Aviso(
                sitio="computrabajo",
                titulo=limpio(a.get_text(" ")),
                url=urljoin(base, a["href"]).split("#")[0],
                empresa=empresa,
                ubicacion=ubic,
                publicado=limpio(fecha.get_text(" ")) if fecha else "",
            )
        )
    if not out:
        out = _desde_json_ld("computrabajo", html, base) or _enlaces_genericos(
            "computrabajo", html, base, r"/ofertas-de-trabajo/oferta-de-trabajo-de-"
        )
    return out


# ---------------------------------------------------------------------- Chiletrabajos
def chiletrabajos(s, palabra: str) -> list[Aviso]:
    base = "https://www.chiletrabajos.cl"
    url = f"{base}/encuentra-un-empleo?2={quote_plus(palabra)}&action=search"
    html = obtener(s, url).text
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for item in soup.select(".job-item"):
        a = item.select_one("h2 a, .title a, a[href*='/trabajo/']")
        if not a or not a.get("href"):
            continue
        meta = item.select_one("h3, .meta")
        empresa, ubic = "", ""
        if meta:
            partes = [limpio(x) for x in meta.get_text("|").split("|") if limpio(x)]
            if partes:
                empresa = partes[0].rstrip(",")
            if len(partes) > 1:
                ubic = partes[-1]
        fecha = item.select_one(".date, h4")
        out.append(
            Aviso(
                sitio="chiletrabajos",
                titulo=limpio(a.get_text(" ")),
                url=urljoin(base, a["href"]),
                empresa=empresa,
                ubicacion=ubic,
                publicado=limpio(fecha.get_text(" ")) if fecha else "",
            )
        )
    if not out:
        out = _desde_json_ld("chiletrabajos", html, base) or _enlaces_genericos(
            "chiletrabajos", html, base, r"chiletrabajos\.cl/trabajo/"
        )
    return out


# ------------------------------------------------------------------------ Trabajando
_CLAVES_TITULO = ("nombreCargo", "titulo", "title", "cargo", "puesto", "nombre")
_CLAVES_ID = ("idOferta", "ofertaId", "offerId", "jobId", "id")


def _buscar_ofertas_json(x, out: list[dict]) -> None:
    if isinstance(x, list):
        for v in x:
            _buscar_ofertas_json(v, out)
    elif isinstance(x, dict):
        tit = next((x[k] for k in _CLAVES_TITULO if isinstance(x.get(k), str)), None)
        oid = next((x[k] for k in _CLAVES_ID if isinstance(x.get(k), (int, str))), None)
        if tit and oid and str(oid).isdigit():
            out.append(x)
        for v in x.values():
            if isinstance(v, (list, dict)):
                _buscar_ofertas_json(v, out)


def _slug(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(txt)).strip("-")[:80]


def _ubicacion_trabajando(o: dict) -> str:
    partes = []
    for k, v in o.items():
        kl = k.lower()
        if not any(x in kl for x in ("comuna", "ciudad", "region", "ubicacion")):
            continue
        if isinstance(v, dict):
            v = v.get("nombre") or v.get("descripcion") or ""
        if isinstance(v, str) and limpio(v) and limpio(v) not in partes:
            partes.append(limpio(v))
    return ", ".join(partes[:2])


def _trabajando_json(data, base: str) -> list[Aviso]:
    crudos: list[dict] = []
    _buscar_ofertas_json(data, crudos)
    out, vistos = [], set()
    for o in crudos:
        tit = next(o[k] for k in _CLAVES_TITULO if isinstance(o.get(k), str))
        oid = str(next(o[k] for k in _CLAVES_ID if isinstance(o.get(k), (int, str))))
        if oid in vistos:
            continue
        vistos.add(oid)
        emp = o.get("nombreEmpresa") or o.get("empresa") or ""
        if isinstance(emp, dict):
            emp = emp.get("nombre") or ""
        out.append(
            Aviso(
                sitio="trabajando",
                titulo=limpio(tit),
                url=f"{base}/trabajo/{oid}-{_slug(tit)}",
                empresa=limpio(str(emp)),
                ubicacion=_ubicacion_trabajando(o),
                publicado=str(o.get("fechaPublicacion") or o.get("fecha") or ""),
            )
        )
    return out


def trabajando(s, palabra: str) -> list[Aviso]:
    """Usa el servicio JSON interno del sitio; si falla, lee la página de búsqueda."""
    base = "https://www.trabajando.cl"
    try:
        r = obtener(
            s,
            f"{base}/api/searchjob?palabraClave={quote(palabra)}",
            headers={"Accept": "application/json"},
        )
        avisos = _trabajando_json(r.json(), base)
        if avisos:
            return avisos
    except Exception:
        pass
    url = f"{base}/trabajo-empleo/{quote(palabra)}"
    html = obtener(s, url).text
    out: list[Aviso] = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, flags=re.S)
    if m:
        try:
            data = json.loads(m.group(1))
        except ValueError:
            data = None
        crudos: list[dict] = []
        _buscar_ofertas_json(data, crudos)
        vistos = set()
        for o in crudos:
            tit = next(o[k] for k in _CLAVES_TITULO if isinstance(o.get(k), str))
            oid = str(next(o[k] for k in _CLAVES_ID if isinstance(o.get(k), (int, str))))
            if oid in vistos:
                continue
            vistos.add(oid)
            emp = o.get("nombreEmpresa") or o.get("empresa") or ""
            if isinstance(emp, dict):
                emp = emp.get("nombre") or ""
            ubic = o.get("ubicacion") or o.get("comuna") or o.get("region") or ""
            if isinstance(ubic, dict):
                ubic = ubic.get("nombre") or ""
            out.append(
                Aviso(
                    sitio="trabajando",
                    titulo=limpio(tit),
                    url=f"{base}/trabajo/{oid}",
                    empresa=limpio(str(emp)),
                    ubicacion=limpio(str(ubic)),
                    publicado=str(o.get("fechaPublicacion") or o.get("fecha") or ""),
                )
            )
    if not out:
        out = _desde_json_ld("trabajando", html, base) or _enlaces_genericos(
            "trabajando", html, base, r"trabajando\.cl/trabajo/\d+"
        )
    return out


LECTORES = {
    "linkedin": linkedin,
    "computrabajo": computrabajo,
    "chiletrabajos": chiletrabajos,
    "trabajando": trabajando,
}
