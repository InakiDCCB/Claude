---
name: feedback-pending-observations
description: Observaciones de sesiones pasadas aún no formalizadas en el spec — pendientes de validación con ≥3 sesiones
metadata:
  type: feedback
---

Observaciones identificadas pero NO implementadas todavía. Validar con ≥3 sesiones de evidencia antes de moverlas al spec en `strategies/pulse_v2.md`.

---

## OBS-1 · Regla de entrada tardía

**Observación (2026-05-20, T5 TSLA):** Entry $0.51 por encima del trigger ideal comprimió el RR a ~1:1 en vez del 2:1 esperado. El trade fue correcto en dirección pero capturó menos ganancia por entrar tarde.

**Regla candidata:** Si `entry_price > trigger_level + 1×ATR(14, 1-min)` → skip the trade. El setup ya corrió demasiado.

**Why:** Con ATR de $0.43, entrar $0.51 tarde significa que el precio ya recorrió más de 1 ATR desde el nivel ideal. El margen para el TP se reduce y el SL queda igual de ancho → RR se destruye.

**How to apply cuando se formalice:** Antes de colocar la orden, calcular `distance = current_price - setup_trigger`. Si `distance > 1×ATR` → pasar al siguiente ciclo.

**Validar:** ¿Cuántas veces en sesiones futuras el precio se aleja >1×ATR del trigger y aun así el trade habría funcionado con buen RR?

---

## OBS-2 · TP2 basado en lower-high

**Observación (2026-05-20):** La teoría lower-high funciona bien en 5-min intraday: si barra N tiene `H[N] < H[N-1]`, el low de esa barra suele ser visitado en las próximas 1-3 barras. Confirmado 3 veces en la sesión del 20-may.

**Regla candidata:** Al buscar TP2, identificar la última barra de 5-min con lower high. Su low es un nivel de liquidez probable → usar como TP2 si está dentro de 5×ATR del entry.

**Why:** Las bajas de barras con lower high acumulan stops de compradores — el precio las visita antes de continuar. Usarlas como target de TP2 aprovecha un movimiento probable en vez de adivinar resistencia.

**How to apply cuando se formalice:** En el ciclo previo a la entrada, escanear las últimas 10 barras de 5-min. Identificar `lower_high_bar = última barra donde H[i] < H[i-1]`. Si `lower_high_bar.low` está entre entry+2×ATR y entry+5×ATR → ese es el TP2 candidato.

**Validar:** ¿Con qué frecuencia el precio alcanza ese nivel antes de revertir? Necesita datos de al menos 3 sesiones.
