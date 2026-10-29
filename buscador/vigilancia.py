"""Vigilancia de páginas: avisa cuando cambia una página de "trabaja con nosotros".

Para centros que publican sus vacantes solo en su propio sitio. En cada chequeo se
descarga la página (respetando su robots.txt), se extrae el texto visible (o solo una
parte, con un selector CSS) y se compara con la versión anterior. Si cambió, se pide
abrir un issue con las líneas nuevas.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from .comun import USER_AGENT, limpio, obtener

MAX_LINEAS = 400


def _permitido(s, url: str, cache: dict) -> bool:
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in cache:
        rp = RobotFileParser()
        try:
            r = s.get(f"{base}/robots.txt", timeout=15)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        cache[base] = rp
    return cache[base].can_fetch(USER_AGENT, url)


def _texto(html: str, selector: str | None) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        t.decompose()
    raiz = soup.select_one(selector) if selector else soup.body or soup
    if raiz is None:
        return []
    lineas, vistas = [], set()
    for linea in raiz.get_text("\n").splitlines():
        linea = limpio(linea)
        if len(linea) >= 3 and linea not in vistas:
            vistas.add(linea)
            lineas.append(linea)
    return lineas[:MAX_LINEAS]


def revisar(s, paginas: list[dict], ruta: Path, t: str) -> tuple[list[dict], list[dict]]:
    """Devuelve (estado por página para mostrar, acciones de issue)."""
    previo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    nuevo, acciones, resumen, robots = {}, [], [], {}
    for pg in paginas or []:
        url, nombre = pg.get("url"), pg.get("nombre") or pg.get("url")
        if not url:
            continue
        ant = previo.get(url, {})
        reg = {"nombre": nombre, "url": url, "revisado": t, "cambiado": ant.get("cambiado"),
               "lineas": ant.get("lineas", []), "hash": ant.get("hash"), "error": ""}
        try:
            if not _permitido(s, url, robots):
                raise PermissionError("el robots.txt del sitio no permite revisarla automáticamente")
            lineas = _texto(obtener(s, url).text, pg.get("selector"))
            if not lineas:
                raise ValueError("no se encontró texto (¿selector incorrecto o página cargada con JavaScript?)")
            h = hashlib.sha1("\n".join(lineas).encode()).hexdigest()
            if reg["hash"] and h != reg["hash"]:
                agregadas = [x for x in lineas if x not in set(reg["lineas"])]
                quitadas = [x for x in reg["lineas"] if x not in set(lineas)]
                reg["cambiado"] = t
                cuerpo = [f"Cambió la página de **{nombre}**: {url}\n"]
                if agregadas:
                    cuerpo.append("**Texto nuevo:**\n" + "\n".join(f"- {x}" for x in agregadas[:25]))
                if quitadas:
                    cuerpo.append("\n**Texto que ya no está:**\n" + "\n".join(f"- ~~{x}~~" for x in quitadas[:10]))
                acciones.append({"accion": "abrir", "titulo": f"🔎 Cambió: {nombre} ({t[:10]})", "cuerpo": "\n".join(cuerpo)})
            reg["hash"], reg["lineas"] = h, lineas
        except Exception as e:
            reg["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        nuevo[url] = reg
        resumen.append({k: reg[k] for k in ("nombre", "url", "revisado", "cambiado", "error")})
    ruta.write_text(json.dumps(nuevo, ensure_ascii=False) + "\n", encoding="utf-8")
    return resumen, acciones
