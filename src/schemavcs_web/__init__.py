"""Web application layer over the schemavcs engine.

Wraps the engine (merge, rename detection, DDL emission) behind an HTTP
API and a server-rendered UI. Never edits `schemavcs/*` -- same principle
as Phase 2 being additive to Phase 1's merge engine without touching it.
"""
