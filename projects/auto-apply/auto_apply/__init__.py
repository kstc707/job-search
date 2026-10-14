"""Guardrails for a Tsenta + Claude job-application pipeline.

The agent does the MCP calls (search, apply); this package holds the deterministic,
testable checks that sit between "Claude wrote a resume" and "Tsenta submits it".
"""
