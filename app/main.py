from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.tickets import router as tickets_router
from app.api.routes.history import router as history_router
from app.api.routes.clients import router as clients_router
from app.api.routes.departments import router as departments_router
from app.api.routes.category import router as categories_router

app = FastAPI(title="Ticket Triage API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(tickets_router, prefix="/tickets")
app.include_router(history_router, prefix="/history")
app.include_router(clients_router, prefix="/clients")
app.include_router(departments_router, prefix="/departments")
app.include_router(categories_router, prefix="/categories")
