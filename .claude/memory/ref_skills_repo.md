---
name: ref-skills-repo
description: Repo git local-only con los skills de usuario pre-market y post-close
metadata:
  type: reference
---

Los skills `pre-market.md` y `post-close.md` viven en `C:\Users\inaki\.claude\commands\` como **repo git independiente, local-only sin remote**.

Decisión 2026-05-28: el usuario rechazó tanto crear repo privado en GitHub como instalar `gh.exe` — ver [[feedback-local-first]].

**Commands para mantenerlo:**
```
git -C "C:/Users/inaki/.claude/commands" status
git -C "C:/Users/inaki/.claude/commands" add <file>
git -C "C:/Users/inaki/.claude/commands" commit -m "..."
```

No proponer `gh repo create`, `git push`, ni instalación de CLIs externas sin volver a preguntar explícitamente.

Estos skills son la fuente que ejecutan los protocolos pre-apertura y post-cierre — su contenido referencia el sistema descrito en [[project-pulse-overview]] y escribe/lee de [[ref-supabase]].
