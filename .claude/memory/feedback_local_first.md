---
name: feedback-local-first
description: Cuando hay alternativa local que funciona, el usuario prefiere local sobre remoto o instalación adicional
metadata:
  type: feedback
---

Si una tarea puede resolverse sin instalar software nuevo y sin crear servicios remotos (GitHub repos, CI, hostings, etc.), proponer la versión local primero. Opciones con `winget install`, `gh repo create`, `npm install -g`, etc. ofrecerlas como **opt-in secundario**, nunca como default.

**Why:** 2026-05-28 — para versionar los skills `pre-market`/`post-close` declinó **tanto** crear repo privado en GitHub **como** instalar `gh.exe`, y pidió textualmente "mejor en local". Patrón coherente con el bias del usuario por mantener el blast radius pequeño (menos dependencias del sistema, menos cuentas externas en la cadena).

**How to apply:**
- `git init` sin remote por defecto. Remote es siempre opt-in.
- Antes de usar una CLI de terceros (`gh`, `aws`, `supabase`, `vercel`, etc.) verificar con `Get-Command <name>` o `(Get-Command <name>).Source` — no asumir que está instalada.
- Cuando una built-in del sistema (PowerShell, git, curl, node, npm) alcanza para la tarea, preferirla sobre instalar algo nuevo.
- Si el remote/install es claramente la solución correcta (ej. trabajo colaborativo, deploy), proponerlo igual pero etiquetándolo como tradeoff explícito.
