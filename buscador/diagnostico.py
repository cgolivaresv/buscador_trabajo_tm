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


def main() -> None:
    OUT.mkdir(exist_ok=True)
    inf: dict = {}
    s = sesion()
    for f in (rss_chiletrabajos, bne, descripciones):
        try:
            f(s, inf)
        except Exception as e:
            inf[f.__name__] = {"error": repr(e)[:300]}
    inf["robots"] = _robots_txt
    (OUT / "diagnostico.json").write_text(json.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(inf, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
