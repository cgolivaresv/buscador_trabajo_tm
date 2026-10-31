"""Diagnóstico de orden y paginación: ¿cómo obtener los avisos MÁS RECIENTES de cada sitio?

Uso:  python -m buscador.diagnostico "tecnologo medico"
Escribe debug/diagnostico.json. Respeta el robots.txt de cada sitio: una dirección no
permitida se informa y no se consulta.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from .comun import USER_AGENT, limpio, sesion

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "debug"
_robots: dict[str, RobotFileParser] = {}


def permitido(s, url: str) -> bool:
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        try:
            r = s.get(base + "/robots.txt", timeout=20)
            rp.parse(r.text.splitlines() if r.ok else [])
        except Exception:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(USER_AGENT, url)


def traer(s, url: str, **kw):
    if not permitido(s, url):
        return None, "bloqueado por robots.txt"
    time.sleep(1.5)
    try:
        r = s.get(url, timeout=30, **kw)
        return r, r.status_code
    except Exception as e:
        return None, repr(e)[:200]


def computrabajo(s, palabra, inf):
    base = "https://cl.computrabajo.com"
    slug = re.sub(r"[^a-z0-9]+", "-", palabra.lower()).strip("-")
    urls = {
        "busqueda": f"{base}/ofertas-de-trabajo/?q={quote_plus(palabra)}",
        "busqueda_p2": f"{base}/ofertas-de-trabajo/?q={quote_plus(palabra)}&p=2",
        "listado": f"{base}/trabajo-de-{slug}",
        "listado_p2": f"{base}/trabajo-de-{slug}?p=2",
        "orden_fecha": f"{base}/ofertas-de-trabajo/?q={quote_plus(palabra)}&by=publicationtime",
    }
    out = {}
    for k, u in urls.items():
        r, st = traer(s, u)
        d = {"url": u, "status": st}
        if r is not None and r.ok:
            soup = BeautifulSoup(r.text, "html.parser")
            arts = soup.select("article.box_offer, article[data-id]")
            d["n"] = len(arts)
            d["fechas"] = [limpio((a.select_one("p.fs13, p.fc_aux") or a).get_text(" "))[:30] for a in arts][:20]
            d["titulos"] = [limpio((a.select_one("h2 a") or a).get_text(" "))[:50] for a in arts][:5]
            d["enlaces_orden"] = sorted({a["href"] for a in soup.select("a[href]") if re.search(r"by=|orden|sort", a["href"])})[:10]
            d["total_texto"] = limpio((soup.select_one("h1") or soup).get_text(" "))[:120]
        out[k] = d
    inf["computrabajo"] = out


def chiletrabajos(s, palabra, inf):
    base = "https://www.chiletrabajos.cl"
    r, st = traer(s, f"{base}/encuentra-un-empleo")
    form = {}
    if r is not None and r.ok:
        soup = BeautifulSoup(r.text, "html.parser")
        for f in soup.select("form"):
            campos = []
            for c in f.select("input[name], select[name]"):
                ops = [(o.get("value"), limpio(o.get_text(" "))) for o in c.select("option")][:12]
                campos.append({"name": c.get("name"), "tipo": c.name, "valor": c.get("value"), "opciones": ops})
            if campos:
                form[f.get("action") or f"form{len(form)}"] = campos
        form["_enlaces_orden"] = sorted({a["href"] for a in soup.select("a[href]")
                                         if re.search(r"orden|order|sort|fecha", a["href"], re.I)})[:15]
    inf["chiletrabajos_formulario"] = form
    pruebas = {
        "actual": f"{base}/encuentra-un-empleo?2={quote_plus(palabra)}&action=search",
        "p2": f"{base}/encuentra-un-empleo/30?2={quote_plus(palabra)}&action=search",
    }
    for o in form.get("_enlaces_orden", [])[:3]:
        pruebas["enlace:" + o[:60]] = urljoin(base, o) + ("&" if "?" in o else "?") + f"2={quote_plus(palabra)}"
    out = {}
    for k, u in pruebas.items():
        r, st = traer(s, u)
        d = {"url": u, "status": st}
        if r is not None and r.ok:
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select(".job-item")
            d["n"] = len(items)
            d["fechas"] = [limpio((i.select_one(".date, h4") or i).get_text(" "))[:40] for i in items][:20]
            d["titulos"] = [limpio((i.select_one("h2 a, .title a") or i).get_text(" "))[:50] for i in items][:5]
            if items:
                d["html_item"] = str(items[0])[:1500]
        out[k] = d
    inf["chiletrabajos"] = out


def trabajando(s, palabra, inf):
    base = "https://www.trabajando.cl"
    cab = {"Accept": "application/json"}
    q = quote(palabra)
    variantes = {
        "actual": f"palabraClave={q}",
        "pagina2": f"palabraClave={q}&pagina=2",
        "page2": f"palabraClave={q}&page=2",
        "orden_fecha": f"palabraClave={q}&orden=FECHA_PUBLICACION",
        "ordenamiento": f"palabraClave={q}&ordenamiento=fecha",
        "sort": f"palabraClave={q}&sort=fecha",
        "estado_cargado": f"palabraClave={q}&estado=CARGADO",
    }
    out = {}
    for k, v in variantes.items():
        r, st = traer(s, f"{base}/api/searchjob?{v}", headers=cab)
        d = {"params": v, "status": st}
        if r is not None and r.ok:
            try:
                j = r.json()
                d["claves"] = list(j.keys())[:30] if isinstance(j, dict) else type(j).__name__
                d["escalares"] = {kk: vv for kk, vv in j.items() if not isinstance(vv, (list, dict))} if isinstance(j, dict) else {}
                of = j.get("ofertas") or []
                d["n"] = len(of)
                d["ids"] = [o.get("idOferta") for o in of][:20]
                d["fechas"] = [o.get("fechaPublicacion") or o.get("fecha") for o in of][:20]
                if of:
                    d["claves_oferta"] = list(of[0].keys())
            except ValueError:
                d["inicio"] = r.text[:300]
        out[k] = d
    r, st = traer(s, f"{base}/trabajo-empleo/{q}")
    if r is not None and r.ok:
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', r.text)[:25]
        hallado = []
        for src in scripts:
            try:
                js = s.get(urljoin(base, src), timeout=25).text
            except Exception:
                continue
            for m in re.finditer(r"searchjob", js):
                hallado.append(js[max(0, m.start() - 400): m.end() + 600])
        out["_contexto_js"] = hallado[:4]
    inf["trabajando"] = out


def laborum(s, palabra, inf):
    base = "https://www.laborum.cl"
    slug = quote(re.sub(r"\s+", "-", palabra.strip().lower()))
    traer(s, f"{base}/empleos-busqueda-{slug}.html")
    out = {}
    for orden in ("RECIENTES", "RELEVANTES"):
        try:
            time.sleep(1.5)
            r = s.post(f"{base}/api/avisos/searchV2?pageSize=40&page=0&sort={orden}",
                       json={"filtros": [], "busquedaExtendida": False, "tipoDetalle": "full", "withHome": False, "query": palabra},
                       headers={"Accept": "application/json", "Content-Type": "application/json", "Origin": base,
                                "Referer": f"{base}/empleos-busqueda-{slug}.html", "x-site-id": "BMCL"}, timeout=30)
            j = r.json()
            out[orden] = {"status": r.status_code, "total": j.get("total"),
                          "fechas": [a.get("fechaPublicacion") for a in j.get("content") or []][:20]}
        except Exception as e:
            out[orden] = {"error": repr(e)[:200]}
    inf["laborum"] = out


def main() -> None:
    palabra = sys.argv[1] if len(sys.argv) > 1 else "tecnologo medico"
    OUT.mkdir(exist_ok=True)
    inf: dict = {"palabra": palabra}
    s = sesion()
    for f in (computrabajo, chiletrabajos, trabajando, laborum):
        try:
            f(s, palabra, inf)
        except Exception as e:
            inf[f.__name__] = {"error": repr(e)[:300]}
    inf["robots"] = {b: "leído" for b in _robots}
    (OUT / "diagnostico.json").write_text(json.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(inf, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main()
