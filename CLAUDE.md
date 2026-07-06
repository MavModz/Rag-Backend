## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).


# Claude Code Master Instructions

This repository is a production-grade RAG system.

Claude must follow ALL rules defined in:
- .claude/AGENTS.md
- .claude/rules.md
- .claude/agents/*.md
- .claude/skills/*/SKILL.md (on-demand)

---

## Execution Principles

1. Always follow architecture separation
2. Never mix API, DB, and RAG logic
3. Always assume production deployment
4. Always consider security risks
5. Always write testable code

---

## Agent Selection Rule

Claude must choose the correct agent based on task:

- Architecture → architect.md
- Backend/API → backend.md
- RAG logic → rag.md
- Security → security.md
- Testing → testing.md
- Code review → reviewer.md

---

## Graphify Rule

If graphify-out exists:
- Use graphify query first before answering architecture questions
- Run graphify update after code changes