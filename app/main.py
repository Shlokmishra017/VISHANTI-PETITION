from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.routers import auth
from app.state_machine import InvalidTransitionError, PermissionDeniedError

app = FastAPI(
    title="Vishanti Petition API",
    description="Tamper-Evident Redressal & Grievance Ledger Backend",
    version="0.1.0"
)

# map invalid transition exceptions to standard api error payload
@app.exception_handler(InvalidTransitionError)
async def invalid_transition_handler(request: Request, exc: InvalidTransitionError):
    status_code = 404 if exc.code == "NOT_FOUND" else 409
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}}
    )

# map permission errors to 403 forbidden
@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
    return JSONResponse(
        status_code=403,
        content={"error": {"code": exc.code, "message": exc.message}}
    )

# register sub-routers with /api prefix
app.include_router(auth.router, prefix="/api")

# health probe
@app.get("/health")
def health_check():
    return {"status": "ok", "system": "vishanti-ledger"}

