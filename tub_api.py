import logging
import asyncio
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from tub_control import cs

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TemperatureSetting(BaseModel):
    temperature: float


class DeviceState(BaseModel):
    state: str


class ModeSetting(BaseModel):
    mode: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.broadcast_task = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        if not self.broadcast_task:
            self.broadcast_task = asyncio.create_task(self.broadcast_loop())

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if not self.active_connections and self.broadcast_task:
            self.broadcast_task.cancel()
            self.broadcast_task = None

    async def broadcast_loop(self):
        while True:
            await asyncio.sleep(1)
            state = cs.get_state()
            await self.broadcast(state)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except RuntimeError as e:
            logger.error(f"Failed to send message: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except RuntimeError as e:
                logger.error(f"Failed to broadcast message: {e}")
                await self.disconnect(connection)

    def close_all(self):
        for connection in self.active_connections:
            connection.close()
            self.disconnect(connection)
        self.active_connections = []


manager = ConnectionManager()


@app.get("/")
async def read_root():
    return FileResponse("index.html")


@app.get("/admin")
async def read_admin():
    return FileResponse("admin.html")


@app.websocket("/state")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive()  # Keep the connection open
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await manager.disconnect(websocket)


@app.get("/quick_state")
async def get_quick_state():
    # Prepare the optimized quick state data
    quick_state = {
        'set_temperature': cs.set_temperature,
        'water_temperature': cs.temp_water.f(),
        'main_pumps': {
            'pump1': cs.pump1.get_state(),
            'pump2': cs.pump2.get_state(),
        },
        'light_state': cs.light.get_state()
    }
    return quick_state


@app.post("/set_temperature")
async def set_temperature(setting: TemperatureSetting):
    cs.set_temperature = setting.temperature
    return {"status": "success", "message": f"Set temperature updated to {setting.temperature}°F."}


@app.post("/toggle/{device}")
async def toggle_device(device: str):
    if device == 'heater':
        cs.heater.toggle_state()
    elif device == 'circpump':
        cs.circpump.toggle_state()
    elif device == 'pump1':
        cs.pump1.advance_state()
    elif device == 'pump2':
        cs.pump2.advance_state()
    elif device == 'blower':
        cs.blower.toggle_state()
    elif device == 'light':
        cs.light.toggle_state()
    elif device == 'ozone':
        cs.ozone.toggle_state()
    elif device == 'fans':
        cs.fans.toggle_state()
    else:
        return {"status": "error", "message": "Unknown device."}
    return {"status": "success", "message": f"{device} toggled."}


@app.post("/set/{device}")
async def set_device_state(device: str, state: DeviceState):
    new_state = state.state.lower()
    if device == 'heater':
        cs.heater.set_state(new_state == "on")
    elif device == 'circpump':
        cs.circpump.set_state(new_state == "on")
    elif device == 'pump1':
        if new_state in ["off", "low", "high"]:
            cs.pump1.set_state(new_state != "off", new_state if new_state != "off" else 'low')
        else:
            return {"status": "error", "message": "Invalid state for pump1."}
    elif device == 'pump2':
        if new_state in ["off", "low", "high"]:
            cs.pump2.set_state(new_state != "off", new_state if new_state != "off" else 'low')
        else:
            return {"status": "error", "message": "Invalid state for pump2."}
    elif device == 'blower':
        cs.blower.set_state(new_state == "on")
    elif device == 'light':
        cs.light.set_state(new_state == "on")
    elif device == 'ozone':  # Add ozone to the set state API
        cs.ozone.set_state(new_state == "on")
    else:
        return {"status": "error", "message": "Unknown device."}
    return {"status": "success", "message": f"{device} state set to {new_state}."}


@app.post("/set_mode")
async def set_mode(setting: ModeSetting):
    mode = setting.mode.lower()
    if mode not in ["automatic", "manual"]:
        return {"status": "error", "message": "Invalid mode. Choose 'automatic' or 'manual'."}
    cs.mode = mode
    return {"status": "success", "message": f"Mode set to {cs.mode}."}


def start_api_server():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


def handle_exit_api(*args):
    logger.info("Received shutdown signal, closing WebSocket connections.")
    manager.close_all()
    asyncio.get_event_loop().stop()
    logger.info("Cleanup complete. Exiting application.")
