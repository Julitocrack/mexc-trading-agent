"""Selección de la regla de señal con indicadores técnicos (capítulo 11) mediante validación por bloques anuales.

Familia de reglas PREDEFINIDA (antes de evaluar):
  estar comprado en t  ⇔  [pronóstico LSTM > δ]  (opcional)
                       ∧  [cierre_t > SMA_w]      (filtro de tendencia, opcional)
                       ∧  [vol20_t < percentil q] (filtro de volatilidad, opcional; q con datos ANTERIORES al bloque)

Selección: bloques anuales consecutivos desde 2019 hasta el final de VA (incluye años alcistas y bajistas).
Criterio: mediana del Sharpe anualizado entre bloques (desempate: peor drawdown). Costo: 5 pb por cambio de posición.

Declaración: el periodo TE ya se CONSULTÓ en un análisis exploratorio previo (2026-11-24). Por eso TE se reporta como
"consultado" y el periodo independiente nuevo es el posterior al último dato de entrenamiento (operación en vivo).

Uso: python -m training.select_strategy
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch  # noqa: F401  (antes que sklearn)
import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.features import FEATURES, supervised  # noqa: E402
from app.model import Predictor, file_sha256, to_input  # noqa: E402

COSTO = 0.0005
DELTAS = [None, 0.0005, 0.001]
VENTANAS = [None, 20, 50, 100, 200]
VOL_Q = [None, 0.70, 0.85]
VERSION = "estrategia-1.1.0"


def metricas(pos, y, costo=COSTO):
    pos = pos.astype(float)
    cambios = np.abs(np.diff(np.concatenate([[0.0], pos])))
    neto = pos * y - cambios * costo
    eq = np.cumprod(1 + neto)
    sd = neto.std()
    return {"rend": float(eq[-1] - 1), "dd": float((eq / np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:] - 1).min()),
            "sharpe": float(neto.mean() / sd * np.sqrt(365)) if sd > 0 else 0.0, "ops": int(cambios.sum()),
            "invertido": float(pos.mean())}


def main() -> None:
    pred_obj = Predictor(BACKEND / "models")
    card = pred_obj.card
    raw = pd.read_csv(BACKEND / "data" / card["data"]["raw_file"])
    assert file_sha256(BACKEND / "data" / card["data"]["raw_file"]) == card["data"]["raw_sha256"], "CSV distinto al del entrenamiento"
    sup = supervised(raw)
    n = len(sup)
    i_va, i_te = int(round(n * 0.70)), int(round(n * 0.85))
    off = len(raw) - n - 1
    close = raw["close"].astype(float)
    c = sup["P"].to_numpy()
    y = sup["y"].to_numpy()
    fechas = pd.to_datetime(sup["fecha_emision"])
    Z = to_input(pred_obj.tipo, pred_obj.esc_x.transform(sup[FEATURES].to_numpy(float)))
    with torch.no_grad():
        pron = pred_obj.net(torch.from_numpy(Z)).numpy() * pred_obj.y_std + pred_obj.y_mean
    sma = {w: close.rolling(w).mean().iloc[off:off + n].to_numpy() for w in VENTANAS if w}
    vol = close.pct_change().rolling(20).std(ddof=1).iloc[off:off + n].to_numpy()

    # Bloques anuales de selección (todos ANTES de TE)
    fin_va = fechas.iloc[i_te - 1]
    bloques = []
    for anio in range(2019, fin_va.year + 1):
        m = ((fechas.dt.year == anio) & (np.arange(n) < i_te)).to_numpy()
        if m.sum() > 60:
            bloques.append((str(anio) if anio < fin_va.year else f"{anio} (hasta {fin_va.date()})", np.where(m)[0]))

    def posicion(delta, w, q, idx):
        delta, w, q = (None if (v is None or pd.isna(v)) else v for v in (delta, w, q))
        w = None if w is None else int(w)
        ok = np.ones(len(idx), bool)
        if delta is not None:
            ok &= pron[idx] > delta
        if w is not None:
            ok &= c[idx] > sma[w][idx]
        if q is not None:
            hist = vol[: idx[0]]                     # percentil con datos ANTERIORES al bloque
            ok &= vol[idx] < np.nanquantile(hist[~np.isnan(hist)], q)
        return ok & ~np.isnan(np.where(w is None, 0, 1) * (sma[w][idx] if w else 0))

    filas = []
    for delta, w, q in itertools.product(DELTAS, VENTANAS, VOL_Q):
        por_bloque = {nombre: metricas(posicion(delta, w, q, idx), y[idx]) for nombre, idx in bloques}
        sh = [m["sharpe"] for m in por_bloque.values()]
        filas.append({"delta": delta, "sma": w, "vol_q": q, "sharpe_mediana": float(np.median(sh)),
                      "peor_dd": float(min(m["dd"] for m in por_bloque.values())),
                      "rend_medio": float(np.mean([m["rend"] for m in por_bloque.values()])), "bloques": por_bloque})
    tabla = pd.DataFrame(filas).sort_values(["sharpe_mediana", "peor_dd"], ascending=[False, False]).reset_index(drop=True)
    best = tabla.iloc[0]
    print("Top 8 por mediana de Sharpe en bloques anuales (2019 → fin de VA):")
    print(tabla.head(8)[["delta", "sma", "vol_q", "sharpe_mediana", "peor_dd", "rend_medio"]].to_string())
    print("\nElegida:", {k: best[k] for k in ("delta", "sma", "vol_q")})
    for nombre, m in best["bloques"].items():
        print(f"  {nombre}: rend {100*m['rend']:+.1f}%  dd {100*m['dd']:.1f}%  sharpe {m['sharpe']:.2f}  ops {m['ops']}")

    # Referencias en los mismos bloques
    bh = {nombre: metricas(np.ones(len(idx), bool), y[idx]) for nombre, idx in bloques}
    actual = {nombre: metricas(pron[idx] > card["signal_threshold"], y[idx]) for nombre, idx in bloques}

    # TE (consultado previamente) y VA, solo para reportar
    idx_va, idx_te = np.arange(i_va, i_te), np.arange(i_te, n)
    def eval_en(idx):
        return metricas(posicion(best["delta"], best["sma"], best["vol_q"], idx), y[idx])
    reporte = {"VA": {"elegida": eval_en(idx_va), "comprar_y_mantener": metricas(np.ones(len(idx_va), bool), y[idx_va]),
                      "regla_v1": metricas(pron[idx_va] > card["signal_threshold"], y[idx_va])},
               "TE_consultado": {"elegida": eval_en(idx_te), "comprar_y_mantener": metricas(np.ones(len(idx_te), bool), y[idx_te]),
                                 "regla_v1": metricas(pron[idx_te] > card["signal_threshold"], y[idx_te])}}
    for k, v in reporte.items():
        print(f"{k}: elegida {100*v['elegida']['rend']:+.1f}% | v1 {100*v['regla_v1']['rend']:+.1f}% | comprar y mantener {100*v['comprar_y_mantener']['rend']:+.1f}%")

    vol_hist = vol[:i_te]
    umbral_vol = None if pd.isna(best["vol_q"]) else float(np.nanquantile(vol_hist[~np.isnan(vol_hist)], best["vol_q"]))
    salida = {
        "version": VERSION, "creada_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modelo": card["version"], "regla": {"delta": None if pd.isna(best["delta"]) else float(best["delta"]),
                                              "sma": None if pd.isna(best["sma"]) else int(best["sma"]),
                                              "vol_q": None if pd.isna(best["vol_q"]) else float(best["vol_q"]),
                                              "vol_umbral": umbral_vol},
        "descripcion": "Comprado si se cumplen todas las condiciones activas; en efectivo si no.",
        "seleccion": {"metodo": "mediana del Sharpe anualizado en bloques anuales 2019 → fin de VA; desempate peor drawdown",
                      "costo_por_cambio": COSTO, "candidatos": len(tabla),
                      "top": tabla.head(8).drop(columns="bloques").to_dict("records"),
                      "bloques_elegida": best["bloques"], "bloques_comprar_y_mantener": bh, "bloques_regla_v1": actual},
        "reporte": reporte,
        "declaracion": ("TE (2025-07-21 → 2026-11-15) se consultó en un análisis exploratorio el 2026-11-24, antes de esta "
                        "selección. Sus resultados se reportan como 'TE consultado', no como evaluación intacta. El periodo "
                        "independiente nuevo es el posterior al 2026-11-16 (operación Paper en vivo)."),
        "advertencia": "Los bloques 2019 → 2024-03 están dentro de TR: allí el pronóstico LSTM es dentro de muestra.",
    }
    (BACKEND / "models" / "strategy_card.json").write_text(json.dumps(salida, indent=2, ensure_ascii=False, default=str))
    print("\nGuardado models/strategy_card.json")


if __name__ == "__main__":
    main()
