---
bp: "BP-01"
name: "scaffold"
title: "Scaffold a new project in the MSpec harness"
init: true
intent: "code"
---

Output ONLY fenced code blocks. Each block starts with ```python followed by the relative path.

Create these files with PRODUCTION-QUALITY code (see Code Quality Rules below):

1. `.harness/bp-01-scaffold/requirements.txt`
   fastapi uvicorn sqlalchemy pydantic python-dotenv alembic

2. `.harness/bp-01-scaffold/main.py`
   FastAPI app with:
   - title="{project_name} API", version="0.1.0"
   - CORS: allow_origins=["*"] (NO allow_credentials when origins is wildcard)
   - GET / returns {"status":"ok","project":"{project_name}","version":"0.1.0"}
   - Lifespan context manager (NOT deprecated on_event) that calls Base.metadata.create_all(bind=engine) on startup
   - uvicorn.run(app, host="0.0.0.0", port=8000) in __main__ block

3. `.harness/bp-01-scaffold/models.py`
   SQLAlchemy 2.0 model FoodEntry:
   - id: int PK autoincrement
   - food_name: str NOT NULL
   - calories: int NOT NULL
   - meal_type: str (breakfast/lunch/dinner/snack)
   - date: date NOT NULL
   - notes: text NULLABLE
   - created_at: datetime default now — use datetime.now(timezone.utc), NOT deprecated utcnow
   - DeclarativeBase from sqlalchemy.orm
   - __repr__ method
   - SQLite URL from env DATABASE_URL default sqlite:///./{project_name}.db
   - engine create_engine with connect_args for SQLite thread safety

4. `.harness/bp-01-scaffold/test_main.py`
   pytest test file with:
   - TestClient from fastapi.testclient
   - test_read_root checks GET / returns 200 and expected keys
   - Uses the app from main module

CODE QUALITY RULES (ALL required):
- Type hints on EVERY function signature (def root() -> dict:)
- Docstrings on every public function and class ("""...""")
- No deprecated APIs: use datetime.now(timezone.utc), NOT utcnow
- No bare except: catch specific exceptions
- Every file under 80 lines
- Test file must pass when run with: pytest .harness/bp-01-scaffold/test_main.py -v