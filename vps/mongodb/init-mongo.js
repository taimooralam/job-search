// MongoDB initialization script for VPS Green environment
// Runs on first container start via docker-entrypoint-initdb.d

// Switch to jobs database
db = db.getSiblingDB('jobs');

// Create application user with appropriate permissions
db.createUser({
  user: 'jobsearch_app',
  pwd: process.env.MONGO_APP_PASSWORD || 'changeme',
  roles: [
    { role: 'readWrite', db: 'jobs' },
    { role: 'dbAdmin', db: 'jobs' }
  ]
});

// Create collections (optional - MongoDB creates on first write)
// These are the known collections from the application
db.createCollection('level-2');
db.createCollection('star_records');
db.createCollection('pipeline_runs');
db.createCollection('master_cv_metadata');
db.createCollection('master_cv_taxonomy');
db.createCollection('master_cv_roles');
db.createCollection('master_cv_history');
db.createCollection('annotation_priors');
db.createCollection('annotation_tracking');
db.createCollection('operation_runs');
db.createCollection('job_search_cache');
db.createCollection('job_search_index');
db.createCollection('application_form_cache');
db.createCollection('system_state');
db.createCollection('company_cache');

print('MongoDB initialization complete - created user and collections');
