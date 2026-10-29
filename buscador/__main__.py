"""Ejecuta un chequeo completo: busca, filtra, fusiona con el historial y guarda.

Uso:  python -m buscador [--nuevos ARCHIVO.md]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import __version__
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
    "indeed": "Indeed",
}


def ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cargar_config() -> dict:
    cfg = yaml.safe_load((RAIZ / "config.yml").read_text(encoding="utf-8")) or {}
    cfg.setdefault("palabras_clave", [])
    cfg.setdefault("excluir", [])
    cfg.setdefault("ubicaciones", [])
    cfg.setdefault("ubicaciones_excluir", [])
    cfg.setdefault("perfil", {})
    cfg.setdefault("solo_afines", False)
    cfg.setdefault("sitios", {k: True for k in LECTORES})
    cfg.setdefault("dias_retencion", 60)
    cfg["_excluir"] = _patrones(cfg["excluir"])
    cfg["_zona_si"] = _patrones(cfg["ubicaciones"])
    cfg["_zona_no"] = _patrones(cfg["ubicaciones_excluir"])
    cfg["_prioritario"] = _patrones((cfg["perfil"] or {}).get("prioritario"))
    cfg["_afin"] = _patrones((cfg["perfil"] or {}).get("afin"))
    cfg["_empresas"] = _patrones((cfg["perfil"] or {}).get("empresas_del_rubro"))
    cfg["_cargos_empresa"] = _patrones((cfg["perfil"] or {}).get("cargos_en_esas_empresas"))
    return cfg


def _patron(termino: str) -> re.Pattern | None:
    """Palabra o frase completa; con * al final, cualquier palabra que empiece así."""
    t = normalizar(str(termino))
    if not t:
        return None
    prefijo = t.endswith("*")
    t = re.escape(t.rstrip("*").strip())
    return re.compile(rf"\b{t}" + ("" if prefijo else r"\b"))


def _patrones(lista) -> list[re.Pattern]:
    return [p for p in map(_patron, lista or []) if p]


def evaluar(titulo: str, ubicacion: str, empresa: str, cfg) -> int:
    """0 = se descarta; 1 = sin relación con el perfil; 2 = afín; 3 = prioritario."""
    tit = normalizar(titulo)
    if any(p.search(tit) for p in cfg["_excluir"]):
        return 0
    ub = normalizar(ubicacion)
    if re.fullmatch(r"[\d.,\s]*", ub):  # sin ubicación o con un dato que no lo es
        ub = ""
    # Zona: se acepta si la ubicación nombra una zona de interés; se descarta si la
    # ubicación o el título ("…para Calama") nombran una zona fuera de interés; si no
    # nombran ninguna conocida (p. ej. solo la comuna), se acepta.
    if cfg["_zona_si"] and not (ub and any(p.search(ub) for p in cfg["_zona_si"])):
        if any(p.search(ub) or p.search(tit) for p in cfg["_zona_no"]):
            return 0
    if any(p.search(tit) for p in cfg["_prioritario"]):
        return 3
    if any(p.search(tit) for p in cfg["_afin"]):
        return 2
    # Fabricantes de equipos: cuenta como afín solo si el cargo es técnico-clínico.
    if any(p.search(normalizar(empresa)) for p in cfg["_empresas"]) and any(
        p.search(tit) for p in cfg["_cargos_empresa"]
    ):
        return 2
    return 0 if cfg["solo_afines"] else 1


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
                if not av.titulo or not av.url:
                    continue
                afinidad = evaluar(av.titulo, av.ubicacion, av.empresa, cfg)
                if not afinidad:
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
                    "afinidad": afinidad,
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
            for k in ("titulo", "empresa", "ubicacion", "publicado"):
                if d[k]:  # se refresca con lo último que muestra el sitio
                    h[k] = d[k]
        else:
            d["encontrado"] = t
            d["visto_ultima_vez"] = t
            historial[aid] = d
            nuevos.append(d)

    limite = datetime.now(timezone.utc) - timedelta(days=int(cfg["dias_retencion"]))
    # El historial se vuelve a evaluar en cada chequeo, por si cambió la configuración.
    for v in historial.values():
        v["afinidad"] = evaluar(v.get("titulo", ""), v.get("ubicacion", ""), v.get("empresa", ""), cfg)
    historial = {
        k: v
        for k, v in historial.items()
        if datetime.fromisoformat(v.get("visto_ultima_vez", t)) >= limite and v["afinidad"]
    }

    lista = sorted(historial.values(), key=lambda a: a.get("encontrado", ""), reverse=True)
    AVISOS.write_text(
        json.dumps({"actualizado": t, "avisos": lista}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    ESTADO.write_text(
        json.dumps(
            {
                "version": __version__,
                "ultimo_chequeo": t,
                "nuevos": len(nuevos),
                "total": len(lista),
                "palabras_clave": cfg["palabras_clave"],
                "zona": cfg.get("zona_nombre") or "",
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
        for d in sorted(nuevos, key=lambda x: -x.get("afinidad", 1)):
            extra = " · ".join(x for x in (d["empresa"], d["ubicacion"]) if x)
            marca = "⭐ " if d.get("afinidad") == 3 else ""
            lineas.append(
                f"- {marca}[{d['titulo']}]({d['url']}) — {NOMBRES.get(d['sitio'], d['sitio'])}"
                + (f" · {extra}" if extra else "")
            )
        Path(args.nuevos).write_text("\n".join(lineas) + "\n", encoding="utf-8")

    sin_ningun_resultado = estado_sitios and all(
        v["resultados"] == 0 and v["errores"] for v in estado_sitios.values()
    )
    return 1 if sin_ningun_resultado else 0


if __name__ == "__main__":
    sys.exit(main())
