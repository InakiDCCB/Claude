---
name: feedback-language
description: Conversación en español; código, specs y archivos de proyecto en su idioma original
metadata:
  type: feedback
---

Texto conversacional (explicaciones, propuestas, resúmenes de cambio, preguntas): **español**.

Contenido de archivos: respetar el idioma del archivo destino.
- Código (Python, TypeScript, SQL): inglés.
- Commit messages: inglés (convención del repo Trading).
- Strategy specs (`pulse_v2.md`, `cycle_prompt.md`): mixto inglés/español — mantener el patrón existente; cabeceras/títulos en español, comandos y nombres técnicos en inglés.
- Schema SQL: inglés, con comentarios bilingües aceptables si el contexto lo pide.
- Memoria interna (este directorio `.claude/memory/`): español, por consistencia con la conversación.

**Why:** el usuario escribe en español a lo largo de toda la sesión 2026-05-28. La base de archivos del proyecto es mixta — predomina inglés en code/schema, mezcla en strategy markdown.

**How to apply:** responder al usuario en español. Al editar un archivo, abrirlo primero (si no se ha leído ya) para verificar idioma dominante y seguir esa convención. No traducir comentarios o secciones existentes salvo que se pida explícitamente.
