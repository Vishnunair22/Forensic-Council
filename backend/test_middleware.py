from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def middle_1(request: Request, call_next):
    print("middle 1 enter")
    response = await call_next(request)
    print("middle 1 exit")
    return response

@app.middleware("http")
async def outer_error(request: Request, call_next):
    print("outer error enter")
    response = await call_next(request)
    print("outer error exit")
    return response

@app.get("/")
def read_root():
    raise Exception("Router crash")

@app.get("/midcrash")
def read_midcrash():
    return {"status": "ok"}
