# CLAUDE.md

Guidance for Claude Code in this repository.

## Project

**News Hub** — a FastAPI news aggregator built step by step, and the source of a Ukrainian-language FastAPI book
(MkDocs + Material for MkDocs + GitHub Pages, `https://nikoriakviktor.github.io/news_hub/`).

It mirrors the Django book `notes_chat_app` (same theme, page templates and rules). The code and the lesson texts come
from the FastAPI branch of the course `PY-Course-Victor-Nikoriak-11-11-2026` (lessons 33, 36–51).

Student-facing documentation is in Ukrainian. Keep code identifiers, commands, API names and paths as they are.

## Layout

```text
steps/NN_<topic>/    full working project at step NN (each with its own README, requirements, tests, CLAUDE.md)
examples/meteo_api/       REST API design example (course lesson 33)
examples/fastapi_vs_drf/  notes API in FastAPI, compared to DRF (course lesson 36)
docs/                     the book
docs/_internal/           audit, inventory, progress — never in the public nav
```

| Step | Folder | Course lesson |
|---|---|---|
| 1 | `steps/01_typing_pydantic` | 37 |
| 2 | `steps/02_fastapi_basics` | 38 |
| 3 | `steps/03_sqlalchemy_alembic` | 39 |
| 4 | `steps/04_middleware_redis` | 40 |
| 5 | `steps/05_api_testing` | 42 |
| 6 | `steps/06_ai_dev_tools` | 43 |
| 7 | `steps/07_llm_api` | 44 |
| 8 | `steps/08_security` | 47 |
| 9 | `steps/09_telegram_bot` | 48 |
| 10 | `steps/10_docker` | 49 |
| 11 | `steps/11_compose_deploy` | 50 |
| 12 | `steps/12_ci_cd` | 51 |

Each step is a snapshot: step N+1 = step N + changes. Never edit one step without checking whether the same change
belongs in the later steps too. `steps/12_ci_cd/CLAUDE.md` holds the app rules (sources, LLM, security, bot, Docker).

## Commands

```bash
cd steps/NN_<topic>
pip install -r requirements.txt            # steps 10–12: requirements-dev.txt
pytest -q                                  # SQLite in memory + fakeredis + FakeLLM; no network
mypy --strict news_hub                     # step 12
pytest -m docker                           # steps 10–12, needs Docker

pip install -r requirements-docs.txt       # repo root
mkdocs build --strict
```

CI: `.github/workflows/steps.yml` (pytest in every step and `examples/meteo_api`), `news_hub.yml` (full CI of
`steps/12_ci_cd`: 2 Pythons, lowest versions, PostgreSQL, mypy, image + smoke, ghcr.io), `docs.yml` (`mkdocs gh-deploy`).

Files with the executable bit (`scripts/*.sh`) live on NTFS with `core.filemode=false`: set the mode in the index,
`git update-index --chmod=+x <file>`, or CI fails with `Permission denied`.

## Source of truth

1. The code in `steps/` (the step the page talks about).
2. Configuration and dependency files of that step.
3. Its tests.
4. `docs/`.
5. The course lesson pages (`docs/modules/m4|m5/lesson_NN.md` in the course repo) — the original texts.

Never invent files, functions, endpoints, fields, settings, environment variables, Docker services, ports,
test results or command output. Do not report a command as successful unless it actually ran successfully;
otherwise say `failed`, `blocked` or `not run` and why.

## Documentation principles

```text
ORGANIZE ≠ SUMMARIZE
REWRITE ≠ SHORTEN
MERGE ≠ DELETE UNIQUE CONTENT
BOOK STRUCTURE ≠ DIRECTORY LIST
```

Moving a lesson into the book keeps its unique explanations, code, diagrams, tables, practice tasks, debugging,
security and production notes. Record every source → book mapping in `docs/_internal/SOURCE_INVENTORY.md`.

- Order inside a section: task → change → result → rule.
- Course-only material (Colab buttons, notebook links, «домашнє завдання до уроку») does not go into the book.
  Instead: a link to `steps/NN/...` and a note «відповідає уроку NN курсу».
- Links to code: `https://github.com/NikoriakViktor/news_hub/blob/main/steps/NN_<topic>/<path>`.
- Explicit heading anchors `{ #id }` for anything linked from another page (Cyrillic slugs are unreliable).

### Page templates

**Knowledge page (Parts I–X):** problem → mental model → concepts → how it works inside → minimal example →
News Hub example → common mistakes → debugging → security → questions → what's next.

**Zero to Hero step:** «Де ми зараз» → problem → what we add → architecture before/after (mermaid) →
files of the step → implementation → walkthrough → check → tests of the step → «Порівняння з попереднім кроком»
(`git diff --no-index`) → what's next.

## English version (i18n)

`mkdocs-static-i18n` with `docs_structure: suffix`. For now only `uk` is enabled. An English page is `page.en.md`
next to `page.md`, with the same headings, code, Mermaid and tables in the same order; menu labels go to
`nav_translations`. Translate explanations only, never code, identifiers, commands or paths.

## Mermaid diagram standards

Same as the Django book. Light palette only, these five classDefs verbatim:

```text
classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;
```

- No inline `style`, no other classDefs, no `mindmap`, no `\n` in labels (use `<br>`), at most 2 lines per node.
- Every algorithm or flow a page explains (request lifecycle, middleware chain, dependency resolution, retries,
  circuit breaker, JWT check…) gets a step-by-step trace: `flowchart TD`, one `subgraph` per step with
  `direction LR`, subgraphs linked to each other, the same data as the code next to it.
- Calls over time (client → nginx → FastAPI → DB/Redis) — `sequenceDiagram`; tables — `erDiagram`.
- Lowercase `так` / `ні` on edges. Check with `mkdocs build --strict` and render in a browser: no «Syntax error in text».

## Git

Commit only when the user asks; never push (the user pushes). Do not rewrite history. Before finishing, show
`git status --short` and `git diff --stat`.
