"""Diagnóstico de un portal: guarda su HTML y busca rutas de API en sus scripts.

Uso:  python -m buscador.diagnostico "tecnologo medico"
Escribe los resultados en la carpeta debug/.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urljoin

from .comun import sesion

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "debug"
BASE = "https://www.trabajando.cl"


def main() -> None:
    palabra = sys.argv[1] if len(sys.argv) > 1 else "tecnologo medico"
    OUT.mkdir(exist_ok=True)
    s = sesion()
    informe: dict = {"palabra": palabra, "paginas": [], "scripts": [], "rutas_api": [], "pruebas": []}

    html = ""
    for url in (f"{BASE}/trabajo-empleo/{quote(palabra)}", f"{BASE}/trabajo-empleo/{quote(palabra.replace(' ', '-'))}"):
        try:
            r = s.get(url, timeout=25)
            informe["paginas"].append({"url": url, "status": r.status_code, "largo": len(r.text),
                                       "enlaces_trabajo": len(re.findall(r'/trabajo/\d+', r.text))})
            if not html and r.ok:
                html = r.text
        except Exception as e:
            informe["paginas"].append({"url": url, "error": repr(e)[:200]})
    (OUT / "trabajando.html").write_text(html[:400_000], encoding="utf-8")

    rutas: set[str] = set()
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html)[:40]:
        url = urljoin(BASE, src)
        try:
            js = s.get(url, timeout=25).text
        except Exception:
            continue
        informe["scripts"].append({"url": url, "largo": len(js)})
        for m in re.findall(r'["\'`]((?:https?://[^"\'`\s]*)?/api/[^"\'`\s]{2,120})["\'`]', js):
            rutas.add(m)
        for m in re.findall(r'["\'`](https?://[a-z0-9.-]*trabajando[a-z0-9.-]*/[^"\'`\s]{0,120})["\'`]', js):
            rutas.add(m)
    informe["rutas_api"] = sorted(rutas)[:300]

    q = quote(palabra)
    candidatos = [
        f"{BASE}/api/searchjob?palabraClave={q}",
        f"{BASE}/api/searchjob?q={q}",
        f"{BASE}/api/ofertas/buscar?palabraClave={q}",
        f"{BASE}/api/v1/ofertas?q={q}",
    ]
    for ruta in informe["rutas_api"]:
        if any(k in ruta.lower() for k in ("search", "busca", "oferta", "job")) and "{" not in ruta:
            candidatos.append(urljoin(BASE, ruta))
    for url in candidatos[:25]:
        try:
            r = s.get(url, timeout=20, headers={"Accept": "application/json"})
            informe["pruebas"].append({"url": url, "status": r.status_code,
                                       "tipo": r.headers.get("content-type", ""), "inicio": r.text[:300]})
        except Exception as e:
            informe["pruebas"].append({"url": url, "error": repr(e)[:200]})

    (OUT / "trabajando.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in informe.items() if k != "scripts"}, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
