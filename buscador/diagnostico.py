"""Diagnóstico de fuentes: prueba direcciones candidatas y guarda lo que responden.

Uso:  python -m buscador.diagnostico "tecnologo medico"
Escribe debug/diagnostico.json, para ajustar los lectores con datos reales.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin

from .comun import sesion

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "debug"

EP = "https://www.empleospublicos.cl"
LB = "https://www.laborum.cl"


def estructura(x, nivel=0):
    """Resumen de un JSON: claves y tipos, con un ejemplo del primer elemento de cada lista."""
    if nivel > 4:
        return "…"
    if isinstance(x, dict):
        return {k: estructura(v, nivel + 1) for k, v in list(x.items())[:60]}
    if isinstance(x, list):
        return [f"lista de {len(x)}", estructura(x[0], nivel + 1)] if x else ["lista vacía"]
    if isinstance(x, str):
        return x[:120]
    return x


def probar(s, nombre, metodo, url, informe, **kw):
    time.sleep(1.5)
    r_inf = {"nombre": nombre, "metodo": metodo, "url": url}
    try:
        r = s.request(metodo, url, timeout=30, **kw)
        r_inf.update(status=r.status_code, tipo=r.headers.get("content-type", ""), largo=len(r.content))
        texto = r.content.decode("utf-8-sig", errors="replace")
        try:
            data = json.loads(texto)
            r_inf["json"] = estructura(data)
        except ValueError:
            r_inf["inicio"] = texto[:1500]
        informe["pruebas"].append(r_inf)
        return r, texto
    except Exception as e:
        r_inf["error"] = repr(e)[:300]
        informe["pruebas"].append(r_inf)
        return None, ""


def rutas_en_scripts(s, base, html, informe, clave):
    rutas: set[str] = set()
    textos = [html]
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html)[:30]:
        try:
            textos.append(s.get(urljoin(base, src), timeout=25).text)
        except Exception:
            continue
    for t in textos:
        for m in re.findall(r'["\'`]((?:https?://[^"\'`\s]*)?/(?:api|data)/[^"\'`\s]{2,140})["\'`]', t):
            rutas.add(m)
        for m in re.findall(r'["\'`]([^"\'`\s]{0,80}\.ashx[^"\'`\s]{0,80})["\'`]', t):
            rutas.add(m)
        for m in re.findall(r'(?i)(x-site-id|siteId|site_id)["\'`]?\s*[:=]\s*["\'`]([A-Z0-9_-]{2,12})', t):
            rutas.add(f"{m[0]}={m[1]}")
    informe[clave] = sorted(rutas)[:200]


def main() -> None:
    palabra = sys.argv[1] if len(sys.argv) > 1 else "tecnologo medico"
    OUT.mkdir(exist_ok=True)
    informe: dict = {"palabra": palabra, "pruebas": []}

    # ---------------- Empleos Públicos: parámetros del servicio /pub/.../apiConvocatorias.ashx
    s = sesion()
    _, html = probar(s, "EP listado", "GET", f"{EP}/pub/convocatorias/convocatorias.aspx", informe)
    textos = [html]
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html)[:30]:
        try:
            textos.append(s.get(urljoin(f"{EP}/pub/convocatorias/", src), timeout=25).text)
        except Exception:
            pass
    informe["ep_contexto"] = []
    for tx in textos:
        for m in re.finditer(r"apiConvocatorias", tx):
            informe["ep_contexto"].append(tx[max(0, m.start() - 700): m.end() + 900])
    api = f"{EP}/pub/convocatorias/apiConvocatorias.ashx"
    cab = {"Accept": "application/json, text/javascript, */*; q=0.01",
           "Referer": f"{EP}/pub/convocatorias/convocatorias.aspx", "X-Requested-With": "XMLHttpRequest"}
    q = quote(palabra)
    for params in ["page=2", "pagina=2", "p=2", "pageSize=100", "size=100", "limit=100", "start=12&length=100",
                   f"q={q}", f"search={q}", f"keyword={q}", f"texto={q}", "region=Regi%C3%B3n%20del%20Maule"]:
        r, texto = probar(s, f"EP api ?{params}", "GET", f"{api}?{params}", informe, headers=cab)
        try:
            d = json.loads(texto)
            informe["pruebas"][-1]["resumen"] = {"total": d.get("total"), "n": len(d.get("data", [])),
                                                 "primero": (d.get("data") or [{}])[0].get("Cargo")}
            informe["pruebas"][-1].pop("json", None)
        except Exception:
            pass

    # ---------------------------------------------------------------- Laborum: enlaces
    s = sesion()
    slug = re.sub(r"\s+", "-", palabra.strip().lower())
    listado = f"{LB}/empleos-busqueda-{quote(slug)}.html"
    probar(s, "LB listado", "GET", listado, informe)
    r, texto = probar(s, "LB api", "POST", f"{LB}/api/avisos/searchV2?pageSize=5&page=0&sort=RECIENTES", informe,
                      json={"filtros": [], "busquedaExtendida": False, "tipoDetalle": "full", "withHome": False, "query": palabra},
                      headers={"Accept": "application/json", "Content-Type": "application/json", "Referer": listado,
                               "Origin": LB, "x-site-id": "BMCL"})
    try:
        av = json.loads(texto)["content"][0]
    except Exception:
        av = None
    if av:
        def sl(x):
            import unicodedata
            x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()
            return re.sub(r"[^a-z0-9]+", "-", x).strip("-")
        cands = [f"{LB}/empleos/{sl(av['titulo'])}-{sl(av.get('empresa'))}-{av['id']}.html",
                 f"{LB}/empleos/{sl(av['titulo'])}-{av['id']}.html",
                 f"{LB}/empleos/{av['id']}.html",
                 f"{LB}/empleos/x-{av['id']}.html"]
        informe["lb_aviso"] = {k: av.get(k) for k in ("id", "titulo", "empresa", "localizacion", "tipoTrabajo")}
        for u in cands:
            time.sleep(1.5)
            try:
                r = s.get(u, timeout=25, allow_redirects=True)
                canon = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', r.text)
                informe["pruebas"].append({"nombre": "LB ficha", "url": u, "status": r.status_code, "final": r.url,
                                           "canonical": canon.group(1) if canon else None,
                                           "tiene_titulo": (av["titulo"][:20] in r.text)})
            except Exception as e:
                informe["pruebas"].append({"nombre": "LB ficha", "url": u, "error": repr(e)[:200]})

    (OUT / "diagnostico.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in informe["pruebas"]:
        print(p.get("status", p.get("error")), p["nombre"], p.get("url", "")[-90:], p.get("resumen", ""))


if __name__ == "__main__":
    main()
