# DEC-001: Reject LangGraph for Orchestration

**Status:** Active
**Date:** 2026-04-23
**Decision:** Use lightweight custom pipeline (`pipeline.py` + `panel.py` + `router.py`, ~400 lines) instead of LangGraph for the orchestration layer.

## Context
An external reviewer recommended LangGraph as the "glue" between our orchestrator components (Planner, Solver, Critic, Human-in-the-Loop), arguing it provides stateful cyclical graphs, persistence, retry logic, and interrupt capabilities natively.

## Arguments For LangGraph
1. **Cyclical loops**: LangGraph models retry/reject cycles as graph edges, avoiding hand-coded state machines
2. **State persistence**: Built-in checkpointing lets you resume failed multi-hour agentic campaigns
3. **Human-in-the-loop**: Native interrupt nodes for approval gates
4. **Extensibility**: Standard graph-based framework familiar to LangChain ecosystem users

## Arguments Against (why we rejected)
1. **We don't have the problem it solves.** Our workflow is human-driven, not autonomous. The "loop" is: human asks → AI builds → tests run → human reviews. That's a checklist, not a graph.
2. **Framework lock-in.** LangGraph owns your control flow. API changes or missing features mean refactoring orchestration instead of doing biology.
3. **Complexity cost.** Contributors must learn LangGraph before they can modify the pipeline. Our 400-line pipeline.py is readable in 5 minutes.
4. **Dependency risk.** LangGraph pulls in langchain-core and related packages — large dependency surface for a scientific project.
5. **Premature abstraction.** We have 2 contributors (1 PM, 1 AI). Formalized multi-agent coordination is a team-of-10 problem.

## Revisit Triggers
- Project grows to 5+ autonomous agents running unsupervised for hours
- Pipeline needs multi-day stateful agentic campaigns without human involvement
- Team grows beyond 2-3 contributors needing formalized agent coordination
- Our custom pipeline.py exceeds ~1,000 lines or becomes hard to maintain

## External Review Context
- Reviewer correctly identified that our plan already has the functional roles (Planner, Solver, Critic, HITL)
- Reviewer's argument was about *implementation strategy*, not *architecture* — they agreed our modules are correct
- We agree LangGraph would be the right choice for a larger team with autonomous agents; it's not the right choice for us today
