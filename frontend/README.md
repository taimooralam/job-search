# Job Search UI

A lightweight Flask + HTMX web interface for managing Level-2 job data from MongoDB.

## Features

- **Table View**: Display jobs with sortable columns (Created, Company, Role, Location, Job ID, Status, Score)
- **Search**: Free-text search across company, title, location, and job ID
- **Pagination**: Configurable page sizes (5, 10, 50, 100 per page)
- **Multi-Select Delete**: Select multiple jobs and delete them in bulk
- **Status Management**: Update job status inline with dropdown (not processed, marked for applying, applied, etc.)
- **Responsive Design**: Works on desktop and mobile browsers

## Tech Stack

- **Backend**: Flask + PyMongo
- **Frontend**: HTMX + Tailwind CSS (CDN)
- **Database**: MongoDB (Level-2 collection)

## Quick Start

### 1. Install Dependencies

```bash
# From the project root
cd /path/to/job-search
source .venv/bin/activate  # Activate virtual environment

# Install Flask if not already installed
pip install flask
```

### 2. Configure Environment

The UI uses the same `MONGODB_URI` from your project's `.env` file.

```bash
# Ensure your .env file has:
MONGODB_URI=mongodb://localhost:27017/jobs
```

### 3. Seed Sample Data (Optional)

```bash
# Add 20 sample jobs
python -m frontend.seed_jobs

# Or add more jobs
python -m frontend.seed_jobs --count 100

# Clear and re-seed
python -m frontend.seed_jobs --clear --count 50
```

### 4. Run the Application

```bash
# From project root
python -m frontend.app

# Or with custom port
FLASK_PORT=8080 python -m frontend.app
```

Open http://localhost:5000 in your browser.

## API Reference

### List Jobs

```
GET /api/jobs
```

Query Parameters:
- `query` - Free-text search (optional)
- `sort` - Field to sort by: createdAt, company, title, location, jobId, status, score (default: createdAt)
- `direction` - Sort direction: asc, desc (default: desc)
- `page` - Page number (default: 1)
- `page_size` - Items per page: 5, 10, 50, 100 (default: 10)

Response:
```json
{
  "jobs": [...],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_count": 150,
    "total_pages": 15,
    "has_prev": false,
    "has_next": true
  }
}
```

### Delete Jobs

```
POST /api/jobs/delete
Content-Type: application/json

{
  "job_ids": ["<ObjectId>", "<ObjectId>", ...]
}
```

Response:
```json
{
  "success": true,
  "deleted_count": 3
}
```

### Update Job Status

```
POST /api/jobs/status
Content-Type: application/json

{
  "job_id": "<ObjectId>",
  "status": "applied"
}
```

Valid statuses:
- `not processed`
- `marked for applying`
- `to be deleted`
- `applied`
- `interview scheduled`
- `rejected`
- `offer received`

Response:
```json
{
  "success": true,
  "job_id": "<ObjectId>",
  "status": "applied"
}
```

### Get Statistics

```
GET /api/stats
```

Response:
```json
{
  "level1_count": 1000,
  "level2_count": 150,
  "status_counts": {
    "not processed": 100,
    "applied": 30,
    ...
  }
}
```

## Project Structure

```
frontend/
├── __init__.py          # Package marker
├── app.py               # Flask application
├── seed_jobs.py         # Sample data seeder
├── README.md            # This file
├── templates/
│   ├── base.html        # Base template with layout
│   ├── index.html       # Main job table page
│   └── partials/
│       └── job_rows.html  # HTMX partial for table rows
└── static/              # Static assets (if needed)
```

## Testing

### Manual Testing Checklist

1. **Search**: Type in search box, verify results filter in real-time
2. **Sort**: Click column headers, verify sort toggles asc/desc
3. **Pagination**: Change page size, navigate pages, verify counts
4. **Delete**: Select jobs, click delete, confirm modal, verify removal
5. **Status**: Change status dropdown, verify toast notification

### Automated Tests

```bash
# Run API smoke tests
pytest frontend/tests/ -v
```

## Development

### Debug Mode

```bash
FLASK_DEBUG=true python -m frontend.app
```

### Custom Port

```bash
FLASK_PORT=8080 python -m frontend.app
```

## Vercel Deployment

### Prerequisites

1. [Vercel CLI](https://vercel.com/cli) installed
2. Vercel account connected
3. MongoDB Atlas cluster (Vercel doesn't support local MongoDB)

### Setup Vercel

```bash
# From frontend/ directory
cd frontend

# Login to Vercel
vercel login

# Link to a project (creates one if it doesn't exist)
vercel link

# Set environment variables
vercel env add MONGODB_URI
# Enter your MongoDB Atlas connection string when prompted
```

### Deploy

```bash
# Preview deployment
vercel

# Production deployment
vercel --prod
```

### GitHub Actions CI/CD

The repository includes a GitHub Actions workflow (`.github/workflows/frontend-ci.yml`) that:

1. **Tests** the frontend on every push/PR to `main` (when frontend files change)
2. **Deploys** to Vercel automatically on push to `main`

To enable automatic deployments, add these secrets to your GitHub repository:

1. **VERCEL_TOKEN**: Get from https://vercel.com/account/tokens
2. **VERCEL_ORG_ID**: Found in `.vercel/project.json` after `vercel link`
3. **VERCEL_PROJECT_ID**: Found in `.vercel/project.json` after `vercel link`

### Environment Variables on Vercel

Set these in Vercel Dashboard → Project → Settings → Environment Variables:

| Variable | Description |
|----------|-------------|
| `MONGODB_URI` | MongoDB Atlas connection string |

## Notes

- The UI operates on the `level-2` collection (scored jobs from the pipeline)
- Status changes are persisted immediately to MongoDB
- Delete operations are permanent and cannot be undone
- Search is case-insensitive and matches partial strings
- **Mobile**: The UI is responsive; on small screens, some columns are hidden for better usability
