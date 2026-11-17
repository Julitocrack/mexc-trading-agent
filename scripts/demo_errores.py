"""Demostración EN VIVO (contra el backend real en 127.0.0.1:8000) de escenarios de error del protocolo.

Complementa las 27 pruebas automatizadas (backend/tests). Cada paso muestra el mensaje útil, el evento registrado
y la ausencia de operaciones indebidas. Requiere el backend en ejecución y `brew services` para Ollama.

Uso: backend/.venv/bin/python scripts/demo_errores.py | tee docs/evidencia/demo_errores_en_vivo.txt
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
KEY = next(l.split("=", 1)[1].strip() for l in (ROOT / "backend/.env").read_text().splitlines() if l.startswith("API_KEY="))
B = "http://127.0.0.1:8000/api"
H = {"X-API-Key": KEY}
c = httpx.Client(timeout=180)


def titulo(t):
    print(f"\n{'=' * 90}\n{t}\n{'=' * 90}", flush=True)


def show(r: httpx.Response, keys=None):
    try:
        body = r.json()
    except ValueError:
        body = r.text
    if keys and isinstance(body, dict):
        body = {k: body.get(k) for k in keys}
    print(f"HTTP {r.status_code} → {json.dumps(body, ensure_ascii=False, default=str)[:600]}")


def eventos(n=3):
    for e in c.get(f"{B}/events?limit={n}", headers=H).json():
        print(f"   bitácora: {e['ts']} [{e['level']}] {e['kind']}: {e['message'][:150]}")


def ordenes():
    return len(c.get(f"{B}/orders", headers=H).json())


titulo("0) Estado inicial")
show(c.get(f"{B}/status", headers=H), ["symbol", "mode", "live_trading_enabled", "agent", "portfolio"])
n0 = ordenes()
print(f"Órdenes Paper registradas: {n0}")

titulo("1) Clave ausente o incorrecta → 401 y registro")
show(c.get(f"{B}/status"))
show(c.post(f"{B}/agent/start", headers={"X-API-Key": "clave-incorrecta"}))
eventos(2)

titulo("2) Evento duplicado: misma vela por segunda vez → no se procesa ni se opera")
show(c.post(f"{B}/agent/cycle", headers=H))
eventos(1)
print(f"Órdenes Paper: {ordenes()} (antes {n0})")

titulo("3) Ollama detenido → mensaje útil, sin inferencia en la nube")
subprocess.run(["brew", "services", "stop", "ollama"], capture_output=True)
time.sleep(3)
show(c.get(f"{B}/llm/health", headers=H))
show(c.post(f"{B}/llm/ask", headers=H, json={"prompt": "di hola"}))
subprocess.run(["brew", "services", "start", "ollama"], capture_output=True)
for _ in range(20):
    time.sleep(1)
    if c.get(f"{B}/llm/health", headers=H).status_code == 200:
        break
print("Ollama reiniciado:")
show(c.get(f"{B}/llm/health", headers=H), ["ollama_version", "model", "descargado", "local"])

titulo("4) Botón de detención: bloquea nuevas órdenes y conserva la posición (no liquida)")
show(c.post(f"{B}/agent/stop", headers=H), ["status", "portfolio"])
show(c.get(f"{B}/status", headers=H), ["agent"])
eventos(1)

titulo("5) Cambiar límites con el agente en ejecución → rechazado; detenido → validado")
c.post(f"{B}/agent/start", headers=H)
show(c.put(f"{B}/config/risk", headers=H, json={"max_exposure_pct": 0.5}))
c.post(f"{B}/agent/pause", headers=H)
show(c.put(f"{B}/config/risk", headers=H, json={"max_exposure_pct": 3}))

titulo("6) Reinicio del backend: estado recuperado de SQLite, vuelve en PAUSA y sin duplicar")
c.post(f"{B}/agent/start", headers=H)
antes = c.get(f"{B}/status", headers=H).json()["portfolio"]
subprocess.run(["pkill", "-f", "uvicorn app.main"])
time.sleep(2)
subprocess.Popen([str(ROOT / "scripts/run_backend.sh")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 start_new_session=True)
for _ in range(30):
    time.sleep(1)
    try:
        if c.get(f"{B}/health").status_code == 200:
            break
    except httpx.HTTPError:
        pass
despues = c.get(f"{B}/status", headers=H).json()
print(f"Antes:   efectivo={antes['cash']:.2f} cantidad={antes['qty']}")
print(f"Después: efectivo={despues['portfolio']['cash']:.2f} cantidad={despues['portfolio']['qty']} | "
      f"estado={despues['agent']['status']} ({despues['agent']['reason']})")
show(c.post(f"{B}/agent/cycle", headers=H))
print(f"Órdenes Paper: {ordenes()} (antes {n0}) → sin duplicados")
eventos(3)
c.post(f"{B}/agent/stop", headers=H)
print("\nFin de la demostración.")
sys.exit(0)
