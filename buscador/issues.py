"""Abre y cierra issues en GitHub según las acciones que deja el chequeo.

Uso (en GitHub Actions, con GH_TOKEN):  python -m buscador.issues acciones.json
Cada acción: {"accion": "abrir"|"cerrar", "titulo": ..., "cuerpo"?: ..., "comentario"?: ...}
No abre un issue si ya hay uno abierto con el mismo título.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def abiertos(titulo: str) -> list[int]:
    datos = json.loads(gh("issue", "list", "--state", "open", "--limit", "100", "--json", "number,title"))
    return [d["number"] for d in datos if d["title"] == titulo]


def main() -> None:
    ruta = Path(sys.argv[1])
    if not ruta.exists():
        return
    for a in json.loads(ruta.read_text(encoding="utf-8")):
        try:
            existentes = abiertos(a["titulo"])
            if a["accion"] == "abrir" and not existentes:
                gh("issue", "create", "--title", a["titulo"], "--body", a.get("cuerpo", ""))
                print("Abierto:", a["titulo"])
            elif a["accion"] == "cerrar":
                for n in existentes:
                    gh("issue", "close", str(n), "--comment", a.get("comentario", "Resuelto."))
                    print("Cerrado:", a["titulo"])
        except subprocess.CalledProcessError as e:
            print(f"No se pudo procesar «{a['titulo']}»: {e.stderr.strip()[:300]}")


if __name__ == "__main__":
    main()
