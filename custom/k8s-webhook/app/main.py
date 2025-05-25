from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json

app = FastAPI()

@app.post("/mutate/pod_limits")
async def mutate_pod_limits(request: Request):
    response = {
        "success": True
    }

    return JSONResponse(content=response)
