# onto-curate
![coverage](https://git.rwth-aachen.de/i5/teaching/kglab/ss2026/onto-curate/badges/main/coverage.svg) 
![pipeline](https://git.rwth-aachen.de/i5/teaching/kglab/ss2026/onto-curate/badges/main/pipeline.svg)
## Prerequisites

- Docker Desktop
- Python 3.12+ (for pre-commit hooks)

## Setup

### 1. Clone the repository

```bash
git clone https://git.rwth-aachen.de/i5/teaching/kglab/ss2026/onto-curate.git
cd onto-curate
```

### 2. Add secrets credentials

```bash
cp backend/secrets.env.example backend/secrets.env
```

Open `backend/secrets.env` and fill in the required values.

### 3. Start the application

```bash
docker compose up --build
```

This starts the following services:

| Service          | URL |
|------------------|---|
| Backend API      | http://localhost:8000 |
| API Swagger Page | http://localhost:8000/docs |
| Frontend         | http://localhost:5173 |

---

## Pre-commit hooks

We use pre-commit to enforce code formatting before every commit. Install it once after cloning:

```bash
pip install pre-commit
pre-commit install
```

The following checks run automatically on `git commit`:

- **autoflake**: removes unused imports
- **isort**: sorts Python imports
- **black**: formats Python code
- **eslint**: lints frontend TypeScript/React files


## Running tests

**Backend:**
```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

**Frontend:**
```bash
cd frontend
npm install
npm test
```
