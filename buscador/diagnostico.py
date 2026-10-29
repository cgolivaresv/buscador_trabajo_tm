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

    # ------------------------------------------------------------ Empleos Públicos
    s = sesion()
    probar(s, "EP robots", "GET", f"{EP}/robots.txt", informe)
    _, html = probar(s, "EP portada", "GET", f"{EP}/", informe)
    _, html2 = probar(s, "EP listado", "GET", f"{EP}/pub/convocatorias/convocatorias.aspx", informe)
    rutas_en_scripts(s, EP, html + html2, informe, "ep_rutas")
    cab = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": f"{EP}/pub/convocatorias/convocatorias.aspx",
        "X-Requested-With": "XMLHttpRequest",
    }
    for f in ("convocatorias2_nueva.txt", "convocatorias2.txt"):
        probar(s, f"EP feed {f}", "GET", f"{EP}/data/{f}", informe, headers=cab)
    for r in [x for x in informe["ep_rutas"] if ".ashx" in x][:5]:
        probar(s, f"EP ruta {r}", "GET", urljoin(f"{EP}/pub/convocatorias/", r), informe, headers=cab)

    # ---------------------------------------------------------------------- Laborum
    s = sesion()
    probar(s, "LB robots", "GET", f"{LB}/robots.txt", informe)
    slug = re.sub(r"\s+", "-", palabra.strip().lower())
    listado = f"{LB}/empleos-busqueda-{quote(slug)}.html"
    _, html = probar(s, "LB listado", "GET", listado, informe)
    rutas_en_scripts(s, LB, html, informe, "lb_rutas")
    informe["lb_listado_enlaces"] = sorted(set(re.findall(r'href="(/empleos/[^"]+\.html)"', html)))[:20]
    m = re.search(r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});", html, flags=re.S)
    if m:
        try:
            informe["lb_estado_inicial"] = estructura(json.loads(m.group(1)))
        except ValueError:
            informe["lb_estado_inicial"] = m.group(1)[:1500]
    cuerpo = {"filtros": [], "busquedaExtendida": False, "tipoDetalle": "full", "withHome": False, "query": palabra}
    for site_id in ("BMCL", "LBCL", "BMLC"):
        probar(
            s,
            f"LB api searchV2 {site_id}",
            "POST",
            f"{LB}/api/avisos/searchV2?pageSize=20&page=0&sort=RELEVANTES",
            informe,
            json=cuerpo,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": listado,
                "Origin": LB,
                "x-site-id": site_id,
            },
        )

    (OUT / "diagnostico.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in informe["pruebas"]:
        print(p.get("status", p.get("error")), p["nombre"], p.get("tipo", ""), p.get("largo", ""))


if __name__ == "__main__":
    main()
