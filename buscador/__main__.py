"""Ejecuta un chequeo completo: busca, filtra, fusiona con el historial y guarda.

Uso:  python -m buscador [--nuevos ARCHIVO.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .comun import normalizar, sesion
from .sitios import LECTORES

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "docs" / "data"
AVISOS = DATOS / "avisos.json"
ESTADO = DATOS / "estado.json"
NOMBRES = {
    "linkedin": "LinkedIn",
    "computrabajo": "Computrabajo",
    "chiletrabajos": "Chiletrabajos",
    "trabajando": "Trabajando.cl",
}


def ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cargar_config() -> dict:
    cfg = yaml.safe_load((RAIZ / "config.yml").read_text(encoding="utf-8")) or {}
    cfg.setdefault("palabras_clave", [])
    cfg.setdefault("excluir", [])
    cfg.setdefault("ubicaciones", [])
    cfg.setdefault("sitios", {k: True for k in LECTORES})
    cfg.setdefault("dias_retencion", 60)
    return cfg


def pasa_filtros(av, cfg) -> bool:
    titulo = normalizar(av.titulo)
    if any(normalizar(x) and normalizar(x) in titulo for x in cfg["excluir"] or []):
        return False
    zonas = [normalizar(z) for z in cfg["ubicaciones"] or [] if normalizar(z)]
    if zonas and av.ubicacion:
        ub = normalizar(av.ubicacion)
        if not any(z in ub for z in zonas):
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nuevos", help="escribe aquí un resumen Markdown de los avisos nuevos")
    args = ap.parse_args()

    cfg = cargar_config()
    DATOS.mkdir(parents=True, exist_ok=True)
    historial: dict[str, dict] = {}
    if AVISOS.exists():
        for a in json.loads(AVISOS.read_text(encoding="utf-8")).get("avisos", []):
            historial[a["id"]] = a
    primera_vez = not historial

    s = sesion()
    t = ahora()
    estado_sitios: dict[str, dict] = {}
    encontrados: dict[str, dict] = {}

    for sitio, lector in LECTORES.items():
        if not cfg["sitios"].get(sitio, False):
            continue
        st = {"nombre": NOMBRES[sitio], "resultados": 0, "errores": []}
        for palabra in cfg["palabras_clave"]:
            try:
                avisos = lector(s, palabra)
            except Exception as e:  # un sitio caído no detiene a los demás
                st["errores"].append(f"«{palabra}»: {type(e).__name__}: {str(e)[:160]}")
                continue
            st["resultados"] += len(avisos)
            for av in avisos:
                if not av.titulo or not av.url or not pasa_filtros(av, cfg):
                    continue
                d = encontrados.get(av.id)
                if d:
                    if palabra not in d["palabras"]:
                        d["palabras"].append(palabra)
                    continue
                encontrados[av.id] = {
                    "id": av.id,
                    "sitio": av.sitio,
                    "titulo": av.titulo,
                    "url": av.url,
                    "empresa": av.empresa,
                    "ubicacion": av.ubicacion,
                    "publicado": av.publicado,
                    "palabras": [palabra],
                }
        estado_sitios[sitio] = st
        print(f"{NOMBRES[sitio]}: {st['resultados']} resultados, {len(st['errores'])} errores")
        for err in st["errores"]:
            print(f"  - {err}")

    nuevos = []
    for aid, d in encontrados.items():
        if aid in historial:
            h = historial[aid]
            h["visto_ultima_vez"] = t
            for p in d["palabras"]:
                if p not in h.setdefault("palabras", []):
                    h["palabras"].append(p)
            for k in ("empresa", "ubicacion", "publicado"):
                if d[k] and not h.get(k):
                    h[k] = d[k]
        else:
            d["encontrado"] = t
            d["visto_ultima_vez"] = t
            historial[aid] = d
            nuevos.append(d)

    limite = datetime.now(timezone.utc) - timedelta(days=int(cfg["dias_retencion"]))
    historial = {
        k: v
        for k, v in historial.items()
        if datetime.fromisoformat(v.get("visto_ultima_vez", t)) >= limite
    }

    lista = sorted(historial.values(), key=lambda a: a.get("encontrado", ""), reverse=True)
    AVISOS.write_text(
        json.dumps({"actualizado": t, "avisos": lista}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    ESTADO.write_text(
        json.dumps(
            {
                "ultimo_chequeo": t,
                "nuevos": len(nuevos),
                "total": len(lista),
                "palabras_clave": cfg["palabras_clave"],
                "sitios": estado_sitios,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Nuevos: {len(nuevos)} · En historial: {len(lista)}")

    # En la primera ejecución todo es "nuevo": se guarda como base sin avisar.
    if args.nuevos and nuevos and not primera_vez:
        lineas = [f"Se encontraron **{len(nuevos)}** avisos nuevos.\n"]
        for d in nuevos:
            extra = " · ".join(x for x in (d["empresa"], d["ubicacion"]) if x)
            lineas.append(
                f"- [{d['titulo']}]({d['url']}) — {NOMBRES.get(d['sitio'], d['sitio'])}"
                + (f" · {extra}" if extra else "")
            )
        Path(args.nuevos).write_text("\n".join(lineas) + "\n", encoding="utf-8")

    sin_ningun_resultado = estado_sitios and all(
        v["resultados"] == 0 and v["errores"] for v in estado_sitios.values()
    )
    return 1 if sin_ningun_resultado else 0


if __name__ == "__main__":
    sys.exit(main())
