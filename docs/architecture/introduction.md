# Introduction

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

This document defines the fullstack architecture for IKIP: backend services, data engineering pipeline, retrieval/RAG orchestration, web application, infrastructure and cross-cutting concerns (security, observability, testing). It is the single source of technical truth for story-driven implementation.

**Starter template:** Greenfield. No starter template; a custom monorepo is defined below to satisfy the local-first / Azure-ready constraint (NFR12, NFR17).

## Change Log

| Date       | Version | Description                                      | Author    |
| ---------- | ------- | ------------------------------------------------ | --------- |
| 2026-11-01 | 0.1     | Initial architecture from PRD (BMAD structuring) | Architect |
