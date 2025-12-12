source .venv/bin/activate && python ./scripts/convert*cv_to_docx.py applications/FILIGRAN/Staff*-_Tech_Lead_Software_Engineer_-\_OpenCTI/CV.md --template ./assets/template-cv.docx

use the prompts/simple-outreach.prompt.md for applications/FILIGRAN/Staff*-\_Tech_Lead_Software_Engineer*-\_OpenCTI/dossier.txt and save to contacts_outreach.txt in the company folder

---

## Local Development

### Start Everything (Docker + Flask) - All in Background

```bash
docker compose -f docker-compose.local.yml down && docker compose -f docker-compose.local.yml up -d --build && FLASK_DEBUG=true .venv/bin/python frontend/app.py > flask.log 2>&1 &
```

### Start Individual Services

**Flask frontend only (port 5000):**

```bash
source .venv/bin/activate && python frontend/app.py
```

**Docker services only (runner:8000 + pdf:8001):**

```bash
docker compose -f docker-compose.local.yml down && docker compose -f docker-compose.local.yml up -d --build
```

### Stop Everything

```bash
docker compose -f docker-compose.local.yml down && pkill -f "python frontend/app.py"
```

### Check Running Processes

```bash
docker ps && ps aux | grep "python frontend/app.py" | grep -v grep
```
