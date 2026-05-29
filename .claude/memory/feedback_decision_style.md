---
name: feedback-decision-style
description: El usuario prefiere propuestas opinionadas con tradeoffs explícitos vía AskUserQuestion, recomendada primero
metadata:
  type: feedback
---

Para decisiones de diseño no triviales: presentar 2–4 opciones concretas con `AskUserQuestion`, recomendada primero y etiquetada `(Recomendado)`, descripciones breves del tradeoff real. No filosofar ni listar contras genéricos.

Cuando el cambio es claro y de bajo riesgo: proponer y ejecutar sin preguntar. El usuario interrumpe (`Request interrupted by user`) si no quiere ese flujo, y eso es señal explícita de "hazlo y deja de preguntar".

**Why:** patrón validado el 2026-05-28 a lo largo de 4–5 decisiones consecutivas sobre Volume Profile (timeframe, rol del filtro, fuente de datos, bin size, scope del repo de skills). El usuario eligió rápido y con confianza en todas. Cuando ofrecí preguntas innecesarias (versionado de memoria, idioma del contenido) las rechazó con "Guarda todo, planea como actualizar la memoria…" — señal clara de que con contexto suficiente para inferir la decisión, no quiere ser preguntado.

**How to apply:**
- Preguntar cuando hay tradeoff real (coste vs precisión, alcance, irreversibilidad, scope ambiguo).
- No preguntar cuando hay default obvio o cuando el comportamiento del usuario en la misma sesión ya da la respuesta.
- En propuestas largas (exploratorias): "2–3 sentences with a recommendation and the main tradeoff. Present it as something the user can redirect" — el usuario corta y dice "vamos con X" rápido.
