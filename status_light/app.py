from fastapi import FastAPI, Request
import asyncio
from kasa import Discover

app = FastAPI()

PLUG_IP = "192.168.1.52"

@app.post("/on-air")
async def update_status(request: Request):
    data = await request.json()
    state = data.get("Availability", "").lower()

    plug = await Discover.discover_single(PLUG_IP)
    await plug.update()

    if state in ["busy", "inameeting", "donotdisturb"]:
        if not plug.is_on:
            await plug.turn_on()
        return {"status": "plug_on"}

    if state in ["available", "away", "offline"]:
        if plug.is_on:
            await plug.turn_off()
        return {"status": "plug_off"}

    return {"status": f"ignored_state: {state}"}