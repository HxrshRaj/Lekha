#!/usr/bin/env bash
# App Service startup command: serve the FastAPI app (and the built React app in ./static if present)
cd /home/site/wwwroot
python -m uvicorn lekha.api:app --host 0.0.0.0 --port "${PORT:-8000}"
