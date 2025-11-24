"""
Vercel serverless function entry point for the Job Search UI.

This file exposes the Flask app as a Vercel serverless function.
Vercel automatically handles the WSGI interface.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import the app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app

# Vercel expects the app to be named 'app' or 'handler'
# The Flask app is already named 'app' so this works directly
