# -*- coding: utf-8 -*-
"""autotest.py — PORTADA de la autovalidacion de computer-use-py.

Entrada UNICA e invariable en los 3 SO: `python autotest.py` (Windows:
`py autotest.py`) DESDE la raiz de esta skill. Solo re-relanza la SUITE
multi-OS scripts/autotest.py con el mismo argv y reutiliza TODO su output
(tabla [funcion | comando | OK/FAIL/SKIP | evidencia] + JSON resumen) y su
exit code, con la consola heredada:

    py autotest.py                  :: modo lectura (defecto, seguro)
    py autotest.py --con-escritura  :: ciclo sandbox del SO (SOLO un humano)

La suite decide por plataforma (FASE SEG2): win32 corre la bateria historica
sobre los CLIs de scripts/; linux/darwin delegan en la suite de su rama
(motor exclusivo); plataforma desconocida responde JSON canonico + exit 2.
Llamada directa avanzada a la suite: py scripts/autotest.py (y las suites de
rama: python3 scripts/linux/autotest.py, python3 scripts/macos/autotest.py).

Este archivo es stdlib-puro (json/os/subprocess/sys): no importa pyautogui ni
APIs del SO, por eso puede ejecutarse en cualquier plataforma antes de tener
las dependencias instaladas — si la suite falta, falla con JSON honesto, no
con traceback.
"""

import json
import os
import subprocess
import sys

# La raiz de la skill es el directorio de ESTE archivo (no depende del CWD).
RAIZ = os.path.dirname(os.path.abspath(__file__))
SUITA = os.path.join(RAIZ, "scripts", "autotest.py")


def main():
    # UTF-8 con reemplazo (mismo borde que los modulos comunes de la skill).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.isfile(SUITA):
        # Contrato de la skill: error JSON + plataforma canonica, exit 2.
        print(json.dumps({
            "error": "falta la suite multi-OS scripts/autotest.py (se movio de "
                     "sitio?): %s" % SUITA,
            "sistema_operativo": sys.platform,
            "plataforma": {"win32": "win", "linux": "linux",
                           "darwin": "darwin"}.get(sys.platform, sys.platform),
        }, ensure_ascii=False))
        sys.exit(2)

    # DELEGAR en la suite: consola heredada (output integro) y exit code tal
    # cual. sys.argv[1:] se reenvia VERBATIM (--con-escritura, etc.).
    proc = subprocess.run([sys.executable, SUITA] + sys.argv[1:])
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
