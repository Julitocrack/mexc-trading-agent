# Evaluación: modelo sin LLM vs agente con LLM vs comprar y mantener

- Modo: **REPLAY** con velas históricas de MEXC (no es conexión en vivo).
- Periodo: 2025-07-21 → 2026-11-15 (482 ciclos de decisión por estrategia); periodo de prueba (TE, ya consultado: ver declaración) del modelo `btcusdt-lstm-1.0.0`.
- Ejecución: decisión al cierre de t, ejecución a la apertura de t+1, valoración al cierre de t+1.
- Estrategia: `estrategia-1.1.0` (δ = 0.10% y precio > SMA50).
- **Declaración:** TE (2025-07-21 → 2026-11-15) se consultó en un análisis exploratorio el 2026-11-24, antes de esta selección. Sus resultados se reportan como 'TE consultado', no como evaluación intacta. El periodo independiente nuevo es el posterior al 2026-11-16 (operación Paper en vivo).
- Costos: comisión 0.00% y deslizamiento 5.0 pb por operación; capital inicial 50,000 USDT; liquidación final al último cierre con costos.
- LLM: `qwen2.5:3b` local (Ollama 0.40.16), duración total 34.5 min.

| Estrategia | Rend. neto | Máx. drawdown | Operaciones (compras/ventas) | Win Rate | Costos (USDT) | Rechazadas | Latencia LLM media (ms) |
|---|---|---|---|---|---|---|---|
| Agente con LLM local | +2.93% | -23.73% | 16/16 | +12.50% | 671.90 | 0 | 4269 |
| Modelo sin LLM (δ = 0.10% y precio > SMA50) | +2.93% | -23.73% | 16/16 | +12.50% | 671.90 | 0 | — |
| Comprar y mantener | -42.55% | -50.46% | 1/0 | no definido | 23.74 | 0 | — |
