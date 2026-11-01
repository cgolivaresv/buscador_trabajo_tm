"""Diagnóstico: BNE (SENCE), RSS de Chiletrabajos y lectura de descripciones completas.

Uso:  python -m buscador.diagnostico
Escribe debug/diagnostico.json. Respeta el robots.txt de cada sitio: una dirección no
permitida se informa y no se consulta.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .comun import USER_AGENT, sesion

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "debug"
_robots: dict[str, RobotFileParser] = {}
_robots_txt: dict[str, str] = {}


def permitido(s, url: str) -> bool:
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        try:
            r = s.get(base + "/robots.txt", timeout=20)
            txt = r.text if r.ok else ""
        except Exception as e:
            txt = ""
            _robots_txt[base] = f"error: {e!r}"[:200]
        _robots_txt.setdefault(base, txt[:2500])
        rp.parse(txt.splitlines())
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


def rss_chiletrabajos(s, inf):
    import xml.etree.ElementTree as ET

    out = {}
    for u in ("https://www.chiletrabajos.cl/rss.xml", "https://www.chiletrabajos.cl/rss.xml?2=tecnologo+medico"):
        r, st = traer(s, u)
        d = {"url": u, "status": st}
        if r is not None and r.ok:
            d["tipo"] = r.headers.get("content-type")
            try:
                root = ET.fromstring(r.content)
                items = root.findall(".//item")
                d["n"] = len(items)
                d["items"] = [{c.tag: (c.text or "")[:160] for c in it} for it in items[:5]]
                d["fechas"] = [(it.findtext("pubDate") or "")[:40] for it in items][:30]
                d["tm"] = [it.findtext("title") for it in items if re.search(r"tecn[oó]logo", it.findtext("title") or "", re.I)][:15]
            except ET.ParseError as e:
                d["inicio"] = r.text[:500]
                d["error_xml"] = str(e)
        out[u] = d
    inf["chiletrabajos_rss"] = out


def bne(s, inf):
    out = {}
    textos = []
    for u in ("https://www.bne.cl/", "https://www.bne.cl/ofertas", "https://www.bne.gob.cl/ofertas",
              "https://www.bne.cl/ofertas?textoLibre=tecnologo+medico", "https://www.bne.cl/ofertas/buscar?q=tecnologo+medico"):
        r, st = traer(s, u, allow_redirects=True)
        d = {"url": u, "status": st}
        if r is not None:
            d["final"] = r.url
            d["tipo"] = r.headers.get("content-type")
            d["largo"] = len(r.text)
            d["titulo"] = (re.search(r"<title>(.*?)</title>", r.text, re.S | re.I) or [None, ""])[1][:120]
            d["enlaces_oferta"] = sorted(set(re.findall(r'href="([^"]*oferta[^"]*)"', r.text, re.I)))[:15]
            d["formularios"] = re.findall(r"<form[^>]*>", r.text, re.I)[:5]
            d["inputs"] = re.findall(r"<(?:input|select)[^>]+name=\"([^\"]+)\"", r.text, re.I)[:30]
            textos.append((r.url, r.text))
        out[u] = d
    rutas = set()
    for base, html in textos:
        for src in re.findall(r'<script[^>]+src="([^"]+)"', html)[:25]:
            try:
                js = s.get(urljoin(base, src), timeout=25).text
            except Exception:
                continue
            for m in re.findall(r'["\'`]((?:https?://[^"\'`\s]*)?/(?:api|ws|servicios?|rest)/[^"\'`\s]{2,140})["\'`]', js):
                rutas.add(m)
            for m in re.finditer(r"ofertas?", js):
                pass
    out["_rutas_js"] = sorted(rutas)[:80]
    inf["bne"] = out


def descripciones(s, inf):
    import trafilatura

    avisos = json.loads((RAIZ / "docs/data/avisos.json").read_text(encoding="utf-8")).get("avisos", [])
    por_sitio: dict[str, list] = {}
    for a in avisos:
        por_sitio.setdefault(a["sitio"], []).append(a["url"])
    por_sitio.setdefault("linkedin", []).append("https://cl.linkedin.com/jobs/view/tecnologo-medico-4300000000")
    out = {}
    for sitio, urls in por_sitio.items():
        for u in urls[:2]:
            r, st = traer(s, u)
            d = {"url": u, "status": st}
            if r is not None and r.ok:
                txt = trafilatura.extract(r.text, include_comments=False, include_tables=True, favor_recall=True) or ""
                d["largo"] = len(txt)
                d["inicio"] = txt[:500]
                d["json_ld"] = "JobPosting" in r.text
            out.setdefault(sitio, []).append(d)
    inf["descripciones"] = out


def bne2(s, inf):
    """Busca la API de búsqueda de ofertas en los scripts de la página de búsqueda y
    revisa cómo viene una ficha de oferta."""
    out = {}
    r, st = traer(s, "https://www.bne.cl/ofertas/buscar?q=tecnologo+medico")
    hallado, rutas = [], set()
    if r is not None and r.ok:
        out["next_data"] = bool(re.search(r"__NEXT_DATA__", r.text))
        for src in re.findall(r'<script[^>]+src="([^"]+)"', r.text)[:60]:
            try:
                js = s.get(urljoin(r.url, src), timeout=25).text
            except Exception:
                continue
            for m in re.findall(r'["\'`]((?:https?://[^"\'`\s]*)?/api/[^"\'`\s]{2,160})["\'`]', js):
                if re.search(r"ofert|busc|search|public|aviso", m, re.I):
                    rutas.add(m)
            for m in re.finditer(r"ofertas?/(?:buscar|busqueda|search|publicas?|listar?)", js, re.I):
                hallado.append(js[max(0, m.start() - 500): m.end() + 700])
    out["rutas"] = sorted(rutas)[:60]
    out["contexto"] = hallado[:5]
    r, st = traer(s, "https://www.bne.gob.cl/ofertas/1598268")
    out["ficha_status"] = st
    if r is not None and r.ok:
        out["ficha_final"] = r.url
        out["ficha_next_data"] = bool(re.search(r"__NEXT_DATA__", r.text))
        out["ficha_json_ld"] = "JobPosting" in r.text
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        out["ficha_next_inicio"] = m.group(1)[:2500] if m else r.text[:1500]
    rr, st2 = traer(s, "https://www.chiletrabajos.cl/rss.xml")
    if rr is not None:
        out["rss_bytes"] = len(rr.content)
    inf["bne2"] = out


def bne3(s, inf):
    """Cómo se llama a /api/ofertas/busqueda: contexto de uso, URL base y pruebas."""
    out = {"contexto": [], "base": []}
    r, st = traer(s, "https://www.bne.cl/ofertas/buscar?q=tecnologo+medico")
    if r is not None and r.ok:
        for src in re.findall(r'<script[^>]+src="([^"]+)"', r.text)[:60]:
            try:
                js = s.get(urljoin(r.url, src), timeout=25).text
            except Exception:
                continue
            for m in re.finditer(r"busquedaBNE|buscarEmpleo\.", js):
                out["contexto"].append(js[max(0, m.start() - 900): m.end() + 900])
            for m in re.finditer(r"baseURL\s*:\s*[^,}]{3,160}|NEXT_PUBLIC_[A-Z_]+\s*[:=]\s*\"[^\"]{3,160}\"", js):
                out["base"].append(m.group(0))
    out["contexto"] = out["contexto"][:6]
    out["base"] = sorted(set(out["base"]))[:20]
    pruebas = []
    cab = {"Accept": "application/json", "Content-Type": "application/json", "Origin": "https://www.bne.cl",
           "Referer": "https://www.bne.cl/ofertas/buscar?q=tecnologo+medico"}
    for host in ("https://www.bne.cl", "https://api.bne.cl", "https://www.bne.gob.cl"):
        for metodo, sufijo, cuerpo in (
            ("GET", "/api/ofertas/busqueda?q=tecnologo%20medico", None),
            ("GET", "/api/ofertas/busqueda?texto=tecnologo%20medico&pagina=0", None),
            ("POST", "/api/ofertas/busqueda", {"texto": "tecnologo medico", "pagina": 0}),
            ("GET", "/api/ofertas/publica/1598268", None),
        ):
            u = host + sufijo
            if not permitido(s, u):
                pruebas.append({"url": u, "status": "bloqueado por robots.txt"}); continue
            time.sleep(1.2)
            try:
                rr = s.request(metodo, u, json=cuerpo, headers=cab, timeout=25)
                pruebas.append({"metodo": metodo, "url": u, "status": rr.status_code, "tipo": rr.headers.get("content-type"),
                                "inicio": rr.text[:700]})
            except Exception as e:
                pruebas.append({"metodo": metodo, "url": u, "error": repr(e)[:160]})
    out["pruebas"] = pruebas
    inf["bne3"] = out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    inf: dict = {}
    s = sesion()
    for f in (bne3,):
        try:
            f(s, inf)
        except Exception as e:
            inf[f.__name__] = {"error": repr(e)[:300]}
    inf["robots"] = _robots_txt
    (OUT / "diagnostico.json").write_text(json.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(inf, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
