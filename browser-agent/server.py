import os
import sys
import json
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import run_agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("browser_agent.server")

app = FastAPI(
    title="Visual Browser Agent Telemetry & Control API",
    description="Real-time control and telemetry streaming backend for pure visual AI browser agent.",
    version="1.0.0"
)

# Enable CORS for Web Dashboard & Chrome Extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for active tasks
task_store: Dict[str, Dict[str, Any]] = {}
active_tasks: Dict[str, asyncio.Task] = {}

class ConnectionManager:
    """Manages active WebSocket telemetry streaming client connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket Client Connected. Total Clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket Client Disconnected. Remaining Clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        to_remove = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to WebSocket client: {e}")
                to_remove.append(connection)

        for conn in to_remove:
            self.disconnect(conn)

manager = ConnectionManager()
loop_handle: Optional[asyncio.AbstractEventLoop] = None

@app.on_event("startup")
async def startup_event():
    global loop_handle
    loop_handle = asyncio.get_running_loop()
    logger.info("FastAPI Visual Telemetry Server Started.")

def sync_step_callback(frame_data: Dict[str, Any]):
    """Sync callback invoked by run_agent step loop to broadcast over WebSocket."""
    global loop_handle
    if loop_handle and loop_handle.is_running():
        # Ensure event key matches spec
        frame_data["event"] = "step_update"
        asyncio.run_coroutine_threadsafe(manager.broadcast(frame_data), loop_handle)

class StartAgentRequest(BaseModel):
    url: str = Field(..., example="https://the-internet.herokuapp.com/login")
    goal: str = Field(..., example="Type 'tomsmith' into Username field, 'SuperSecretPassword!' into Password field, and click Login button")
    max_steps: int = Field(default=15, ge=1, le=30)
    width: int = Field(default=1280, ge=640, le=2560)
    height: int = Field(default=800, ge=480, le=1440)
    mode: str = Field(default="hybrid", example="hybrid")

class StartAgentResponse(BaseModel):
    task_id: str
    status: str
    message: str

def execute_agent_task(task_id: str, goal: str, url: str, max_steps: int, width: int, height: int, disable_vision: bool):
    """Worker wrapper executed in background thread."""
    task_store[task_id]["status"] = "running"
    try:
        summary = run_agent(
            goal=goal,
            url=url,
            max_steps=max_steps,
            headless=True,
            disable_vision=disable_vision,
            task_id=task_id,
            step_callback=sync_step_callback
        )
        task_store[task_id]["status"] = "completed"
        task_store[task_id]["summary"] = summary
    except Exception as e:
        logger.error(f"Task {task_id} failed with exception: {e}")
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["error"] = str(e)

@app.post("/api/agent/start", response_model=StartAgentResponse)
async def start_agent(request: StartAgentRequest):
    task_id = str(uuid.uuid4())
    disable_vision = (request.mode.lower() == "dom")

    task_store[task_id] = {
        "task_id": task_id,
        "goal": request.goal,
        "url": request.url,
        "max_steps": request.max_steps,
        "width": request.width,
        "height": request.height,
        "mode": request.mode,
        "status": "started",
        "summary": None,
        "error": None
    }

    # Run agent in background thread to avoid blocking FastAPI event loop
    async_task = asyncio.create_task(
        asyncio.to_thread(
            execute_agent_task,
            task_id,
            request.goal,
            request.url,
            request.max_steps,
            request.width,
            request.height,
            disable_vision
        )
    )
    active_tasks[task_id] = async_task

    return StartAgentResponse(
        task_id=task_id,
        status="started",
        message=f"Agent task {task_id} started successfully."
    )

@app.get("/api/agent/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return task_store[task_id]

@app.post("/api/agent/stop/{task_id}")
async def stop_agent(task_id: str):
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

    if task_id in active_tasks:
        async_task = active_tasks[task_id]
        async_task.cancel()
        del active_tasks[task_id]

    task_store[task_id]["status"] = "cancelled"
    return {"task_id": task_id, "status": "cancelled", "message": "Agent task cancelled gracefully."}

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message from client: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)

# Mount Dashboard static directory if it exists
dashboard_dir = Path(__file__).resolve().parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

@app.get("/")
async def root():
    return {
        "service": "Visual Browser Agent Telemetry & Control Server",
        "dashboard": "/dashboard/",
        "websocket": "ws://localhost:8000/ws/telemetry",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
