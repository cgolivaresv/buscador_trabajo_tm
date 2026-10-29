"""Un lector por portal. Cada función recibe una palabra clave y devuelve avisos.

Los portales cambian su HTML de vez en cuando. Cada lector prueba primero la
estructura conocida y, si no encuentra nada, cae a una lectura genérica de los
enlaces a avisos, para seguir funcionando aunque cambie el diseño.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
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
        av = Aviso(
            sitio=sitio,
            titulo=limpio(o["title"]),
            url=urljoin(base, url),
            empresa=limpio(org.get("name") if isinstance(org, dict) else ""),
            ubicacion=ubic,
            publicado=str(o.get("datePosted") or ""),
            cierre=str(o.get("validThrough") or "")[:10],
        )
        sal = o.get("baseSalary")
        if isinstance(sal, dict):
            val = sal.get("value")
            if isinstance(val, dict):
                lo, hi = val.get("minValue"), val.get("maxValue") or val.get("value")
                if lo or hi:
                    av.renta = " a ".join(f"${int(float(x)):,}".replace(",", ".") for x in (lo, hi) if x)
        tipo = o.get("employmentType")
        if isinstance(tipo, list):
            tipo = ", ".join(map(str, tipo))
        if isinstance(tipo, str):
            av.completar_desde_texto(tipo.replace("_", " "))
        out.append(av.completar_desde_texto(""))
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
            ).completar_desde_texto("")
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
        # La ubicación es el primer texto que no sea la nota de la empresa (4,2),
        # la fecha ("Hace 2 horas") ni el nombre de la empresa.
        for el in art.select("p span") + ps[1:]:
            txt = limpio(el.get_text(" "))
            if (
                not txt
                or re.fullmatch(r"[\d.,\s]+", txt)
                or txt.lower().startswith(("hace", "ayer", "hoy"))
                or (empresa and empresa in txt)
                or "$" in txt
            ):
                continue
            ubic = re.sub(r"^[\d.,\s]+", "", txt)
            break
        fecha = art.select_one("p.fs13, p.fc_aux")
        out.append(
            Aviso(
                sitio="computrabajo",
                titulo=limpio(a.get_text(" ")),
                url=urljoin(base, a["href"]).split("#")[0],
                empresa=empresa,
                ubicacion=ubic,
                publicado=limpio(fecha.get_text(" ")) if fecha else "",
            ).completar_desde_texto(art.get_text(" "))
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
            ).completar_desde_texto(item.get_text(" "))
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
        av = Aviso(
            sitio="trabajando",
            titulo=limpio(tit),
            url=f"{base}/trabajo/{oid}-{_slug(tit)}",
            empresa=limpio(str(emp)),
            ubicacion=_ubicacion_trabajando(o),
            publicado=str(o.get("fechaPublicacion") or o.get("fecha") or ""),
        )
        # Detalle: se buscan campos por nombre aproximado, ya que el formato no es público.
        extra = []
        for k, v in o.items():
            kl = k.lower()
            if isinstance(v, dict):
                v = v.get("nombre") or v.get("descripcion") or ""
            if not isinstance(v, (str, int, float)) or v in ("", 0):
                continue
            if any(x in kl for x in ("sueldo", "renta", "salario")) and not av.renta:
                av.renta = f"${int(v):,}".replace(",", ".") if isinstance(v, (int, float)) else limpio(str(v))
            elif any(x in kl for x in ("cierre", "expira", "vencimiento", "fechafin")) and not av.cierre:
                av.cierre = str(v)[:10]
            elif any(x in kl for x in ("jornada", "contrato", "horario")):
                extra.append(str(v))
        out.append(av.completar_desde_texto(" ".join(extra)))
    return out


_STOP = {"de", "del", "la", "el", "en", "con", "y", "para", "por", "los", "las"}
_SITEMAP: dict[str, list[tuple[str, str]]] = {}


def _sitemap_trabajando(s, base: str) -> list[tuple[str, str]]:
    """Lista (url, lastmod) de todas las ofertas vigentes; se descarga una vez por chequeo."""
    if "ofertas" in _SITEMAP:
        return _SITEMAP["ofertas"]
    xml = obtener(s, f"{base}/sitemap-ofertas.xml").text
    hijos = re.findall(r"<sitemap>.*?<loc>\s*([^<\s]+)\s*</loc>", xml, flags=re.S)
    textos = [xml] if not hijos else [obtener(s, h).text for h in hijos[:10]]
    entradas = []
    for x in textos:
        for bloque in re.findall(r"<url>(.*?)</url>", x, flags=re.S):
            loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", bloque)
            mod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", bloque)
            if loc and "/trabajo/" in loc.group(1):
                entradas.append((loc.group(1), mod.group(1) if mod else ""))
    _SITEMAP["ofertas"] = entradas
    return entradas


def _calza_slug(palabra: str, slug: str) -> bool:
    """Todas las palabras importantes de la búsqueda aparecen en la URL del aviso."""
    tokens = slug.split("-")
    claves = [w for w in normalizar(palabra).split() if len(w) >= 3 and w not in _STOP]
    return bool(claves) and all(
        any(tk.startswith(w[: min(len(w), 6)]) for tk in tokens) for w in claves
    )


def _trabajando_sitemap(s, palabra: str, base: str, dias: int = 30, max_detalle: int = 10) -> list[Aviso]:
    limite = (datetime.now(timezone.utc) - timedelta(days=dias)).date().isoformat()
    hallados = []
    for url, mod in _sitemap_trabajando(s, base):
        if mod and mod[:10] < limite:
            continue
        m = re.search(r"/trabajo/(\d+)-([a-z0-9-]+)", url)
        if m and _calza_slug(palabra, m.group(2)):
            hallados.append((mod, url, m.group(2)))
    hallados.sort(reverse=True)
    out = []
    for n, (mod, url, slug) in enumerate(hallados[:40]):
        av = Aviso(sitio="trabajando", titulo=slug.replace("-", " ").capitalize(), url=url, publicado=mod)
        if n < max_detalle:  # completa empresa y ubicación desde la ficha del aviso
            try:
                ld = _desde_json_ld("trabajando", obtener(s, url).text, base)
                if ld:
                    av.titulo = ld[0].titulo or av.titulo
                    av.empresa, av.ubicacion = ld[0].empresa, ld[0].ubicacion
            except Exception:
                pass
        out.append(av)
    return out


def trabajando(s, palabra: str) -> list[Aviso]:
    """Prueba en orden: servicio JSON del sitio, sitemap de ofertas y página de búsqueda."""
    base = "https://www.trabajando.cl"
    fallas = []
    try:
        r = obtener(
            s,
            f"{base}/api/searchjob?palabraClave={quote(palabra)}",
            headers={"Accept": "application/json"},
        )
        avisos = _trabajando_json(r.json(), base)
        if avisos:
            return avisos
        fallas.append("servicio JSON sin ofertas")
    except Exception as e:
        fallas.append(f"servicio JSON: {type(e).__name__}")
    try:
        avisos = _trabajando_sitemap(s, palabra, base)
        if avisos:
            return avisos
        fallas.append("sitemap sin coincidencias")
    except Exception as e:
        fallas.append(f"sitemap: {type(e).__name__}")
    try:
        html = obtener(s, f"{base}/trabajo-empleo/{quote(palabra)}").text
        avisos = _desde_json_ld("trabajando", html, base) or _enlaces_genericos(
            "trabajando", html, base, r"trabajando\.cl/trabajo/\d+"
        )
        if avisos:
            return avisos
        fallas.append("página de búsqueda sin avisos")
    except Exception as e:
        fallas.append(f"página de búsqueda: {type(e).__name__}")
    # Si todas las vías respondieron pero no hay avisos, simplemente no hay resultados.
    if all(f.endswith(("sin ofertas", "sin coincidencias", "sin avisos")) for f in fallas):
        return []
    # Si alguna vía falló de verdad, se informa como error para que se vea qué se intentó.
    raise RuntimeError("; ".join(fallas))


# ----------------------------------------------------------------------------- Indeed
def _jobspy(sitio: str, **kw) -> list[Aviso]:
    """Lee un sitio a través de la librería JobSpy y convierte sus filas en avisos."""
    from jobspy import scrape_jobs

    df = scrape_jobs(site_name=[sitio], verbose=0, **kw)
    errores = (getattr(df, "attrs", {}) or {}).get("errors") or {}
    if df.empty and errores:
        raise RuntimeError(str(errores)[:200])
    ok = lambda v: v is not None and v == v and str(v) != ""  # descarta None y NaN
    out = []
    for fila in df.to_dict("records"):
        url = fila.get("job_url") if ok(fila.get("job_url")) else fila.get("job_url_direct")
        if not ok(url) or not ok(fila.get("title")):
            continue
        lo, hi = fila.get("min_amount"), fila.get("max_amount")
        renta = " a ".join(
            f"${int(x):,}".replace(",", ".") for x in (lo, hi) if isinstance(x, (int, float)) and ok(x) and x > 0
        )
        tipo = str(fila.get("job_type")) if ok(fila.get("job_type")) else ""
        out.append(
            Aviso(
                sitio=sitio,
                titulo=limpio(str(fila["title"])),
                url=str(url),
                empresa=limpio(str(fila["company"])) if ok(fila.get("company")) else "",
                ubicacion=limpio(str(fila["location"])) if ok(fila.get("location")) else "",
                publicado=str(fila["date_posted"]) if ok(fila.get("date_posted")) else "",
                renta=renta,
            ).completar_desde_texto(tipo.replace("fulltime", "full time").replace("parttime", "part time"))
        )
    return out


def indeed(s, palabra: str) -> list[Aviso]:
    """Indeed Chile (cl.indeed.com), avisos de las últimas 2 semanas."""
    return _jobspy(
        "indeed",
        search_term=palabra,
        location="Chile",
        country_indeed="Chile",
        results_wanted=30,
        hours_old=24 * 14,
    )


def google(s, palabra: str) -> list[Aviso]:
    """Google Empleos: reúne avisos de muchos portales y de páginas propias de empresas.
    Google bloquea a veces las consultas desde servidores; en ese caso se informa el error."""
    try:
        # Formato de consulta que espera JobSpy: "<cargo> jobs near Chile in the last week".
        return _jobspy("google", search_term=palabra, location="Chile", hours_old=24 * 7, results_wanted=20)
    except RuntimeError as e:
        raise RuntimeError(f"{e} · {_diagnostico_google(s, palabra)}") from None


def _diagnostico_google(s, palabra: str) -> str:
    """Explica por qué Google no entregó empleos (bloqueo, consentimiento o sin resultados)."""
    try:
        r = s.get("https://www.google.com/search", params={"q": f"{palabra} jobs near Chile", "udm": "8"}, timeout=20)
        t = r.text.lower()
        if r.status_code == 429 or "unusual traffic" in t or "/sorry/" in r.url:
            return "Google bloqueó la consulta (tráfico inusual desde el servidor)"
        if "consent.google" in r.url or "before you continue" in t:
            return "Google pidió aceptar cookies (página de consentimiento)"
        return f"Google respondió {r.status_code} sin el panel de empleos"
    except Exception as e:  # el diagnóstico nunca debe romper el chequeo
        return f"sin diagnóstico ({type(e).__name__})"


# ---------------------------------------------------------------------------- Laborum
_LB = "https://www.laborum.cl"


def _laborum_url(av: dict) -> str:
    return f"{_LB}/empleos/{_slug(av.get('titulo', ''))}-{_slug(av.get('empresa') or '')}-{av['id']}.html".replace(
        "--", "-"
    )


def laborum(s, palabra: str) -> list[Aviso]:
    """API interna del sitio (la misma que usa su buscador). Pide visitar el listado
    antes, para tener las cookies, y el encabezado x-site-id de Laborum Chile."""
    slug = quote(re.sub(r"\s+", "-", palabra.strip().lower()))
    listado = f"{_LB}/empleos-busqueda-{slug}.html"
    if not s.cookies.get_dict(domain=".laborum.cl") and not s.cookies.get_dict(domain="www.laborum.cl"):
        obtener(s, listado)
    time.sleep(1.0)
    r = s.post(
        f"{_LB}/api/avisos/searchV2?pageSize=40&page=0&sort=RECIENTES",
        json={"filtros": [], "busquedaExtendida": False, "tipoDetalle": "full", "withHome": False, "query": palabra},
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": listado,
            "Origin": _LB,
            "x-site-id": "BMCL",
        },
        timeout=25,
    )
    r.raise_for_status()
    out = []
    for av in r.json().get("content") or []:
        if not av.get("id") or not av.get("titulo"):
            continue
        empresa = "" if av.get("confidencial") else limpio(av.get("empresa") or "")
        fecha = av.get("fechaPublicacion") or ""
        m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", fecha)
        out.append(
            Aviso(
                sitio="laborum",
                titulo=limpio(av["titulo"]),
                url=_laborum_url(av),
                empresa=empresa,
                ubicacion=limpio(av.get("localizacion") or ""),
                publicado=f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else fecha,
            ).completar_desde_texto(" ".join(str(av.get(k) or "") for k in ("tipoTrabajo", "detalle")))
        )
    return out


LECTORES = {
    "linkedin": linkedin,
    "computrabajo": computrabajo,
    "chiletrabajos": chiletrabajos,
    "trabajando": trabajando,
    "indeed": indeed,
    "google": google,
    "laborum": laborum,
}
