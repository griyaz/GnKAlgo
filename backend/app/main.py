from fastapi import FastAPI

# Import the instruments router we added earlier
# Make sure package __init__.py files exist so this import works
from backend.app.api.api_v1.endpoints import instruments

app = FastAPI(title="GnKAlgo API")

# Register instruments router under /api/v1/instruments
app.include_router(instruments.router, prefix="/api/v1/instruments", tags=["instruments"])

@app.get("/health")
def health():
    return {"status": "ok"}
