"""FastAPI entrypoint — deliberately thin.

Responsibilities: CORS, request validation, error handling, and handing
work to the agent. No clinical logic here.

Routes (step 2+):
    GET  /health
    POST /analyze_labs        JSON body  -> classified + explained results
    POST /analyze_labs/csv    file upload -> same response shape
"""
