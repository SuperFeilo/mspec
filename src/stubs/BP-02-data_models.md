---
bp: "BP-02"
name: "data-models"
title: "Define data models with SQLAlchemy 2.0 + Pydantic schemas"
init: false
intent: "code"
tech_stack:
  lang: "Python"
  framework: "FastAPI + SQLAlchemy 2.0 + Pydantic v2"
---

# BP-02: Data Models

## Context

The project needs persistent data models and corresponding Pydantic schemas
for API validation/serialization. This stub creates a clean models + schemas
layer following SQLAlchemy 2.0 declarative style and Pydantic v2 conventions.

## Task

Output ONLY fenced code blocks. Each block starts with ```python followed by the relative path.

Create these files with PRODUCTION-QUALITY code:

1. **`src/models.py`** — SQLAlchemy 2.0 declarative models
   - DeclarativeBase from sqlalchemy.orm
   - At least 2 related models with a foreign key relationship
   - Column types: Integer (PK), String, Text, DateTime, Boolean, ForeignKey
   - `created_at` / `updated_at` using `datetime.now(timezone.utc)` — NO deprecated `utcnow`
   - `__repr__` on every model
   - SQLite engine via `DATABASE_URL` env var (default `sqlite:///./app.db`)
   - `connect_args={"check_same_thread": False}` for SQLite

2. **`src/schemas.py`** — Pydantic v2 schemas
   - `BaseModel` from `pydantic`
   - `model_config = ConfigDict(from_attributes=True)` for ORM mode (NOT `orm_mode = True`)
   - Create, Update, and Response schemas for each model
   - Field validators where appropriate (e.g. string length, numeric ranges)
   - `model_dump()` instead of deprecated `dict()`

3. **`src/database.py`** — Session management
   - `get_db()` async generator using `SessionLocal`
   - `init_db()` lifespan function
   - `engine` and `SessionLocal` at module level

## Constraints

- Type hints on EVERY function signature and EVERY model column
- Docstrings on every public function and class
- No bare `except:` — catch specific exceptions
- No deprecated Pydantic v1 APIs (`orm_mode`, `dict()`, `parse_obj`)
- No deprecated SQLAlchemy patterns (`declarative_base()` function)
- Each file under 100 lines

## Acceptance Criteria

1. `from src.models import Base, ModelA, ModelB` imports without error
2. `from src.schemas import ModelACreate, ModelAResponse, ModelBCreate, ModelBResponse` imports without error
3. `pytest`-compatible: schemas pass round-trip validation with sample data
4. No deprecation warnings at import time
