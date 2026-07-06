"""Agent Orchestrator (RESERVED — not implemented in M1).

Boundary: receive user intent, select the correct agent (Support, Quiz, Meeting,
CRM, LMS, Requirement, Document, ...), and run it. Each agent knows only business
logic and never calls models directly — they go through the Model Gateway.
See README.md.
"""
