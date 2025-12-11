from fastapi import FastAPI, Request
import asyncio
from kasa import Discover
import threading
import winreg
import time

app = FastAPI()

PLUG_IP = "192.168.1.52"

# Global state
mic_active = False
camera_active = False
etw_thread = None

async def update_plug_state(should_be_on: bool):
    """Update the plug state based on mic/camera status"""
    try:
        plug = await Discover.discover_single(PLUG_IP)
        await plug.update()
        
        if should_be_on and not plug.is_on:
            await plug.turn_on()
            print("🔴 ON AIR - Plug turned ON")
        elif not should_be_on and plug.is_on:
            await plug.turn_off()
            print("⚫ OFF AIR - Plug turned OFF")
    except Exception as e:
        print(f"Error updating plug: {e}")


def check_device_in_use(device_type):
    """Check if camera or microphone is in use via Windows registry"""
    try:
        base_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
        device_path = f"{base_path}\\{device_type}"
        
        # Open the main device key
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, device_path) as key:
            try:
                # Check main key timestamps
                last_used_start, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")
                last_used_stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")
                
                if last_used_start > last_used_stop:
                    return True
            except FileNotFoundError:
                pass
        
        # Also check NonPackaged subkeys for desktop apps
        try:
            nonpackaged_path = f"{device_path}\\NonPackaged"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, nonpackaged_path) as np_key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(np_key, i)
                        app_path = f"{nonpackaged_path}\\{subkey_name}"
                        
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, app_path) as app_key:
                            try:
                                last_used_start, _ = winreg.QueryValueEx(app_key, "LastUsedTimeStart")
                                last_used_stop, _ = winreg.QueryValueEx(app_key, "LastUsedTimeStop")
                                
                                if last_used_start > last_used_stop:
                                    print(f"  {device_type} in use by: {subkey_name.split('#')[-1]}")
                                    return True
                            except FileNotFoundError:
                                pass
                        
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            pass
            
    except Exception as e:
        print(f"Registry check error for {device_type}: {e}")
    
    return False


def check_camera_mic():
    """Check both camera and microphone status"""
    camera_active = check_device_in_use("webcam")
    mic_active = check_device_in_use("microphone")
    return camera_active, mic_active


def monitor_devices():
    """Background thread that monitors mic and camera state"""
    global mic_active, camera_active
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("📡 Device monitoring started")
    
    while True:
        try:
            camera_now, mic_now = check_camera_mic()
            
            state_changed = (mic_now != mic_active) or (camera_now != camera_active)
            print(f"🎤 Mic: {mic_now} | 📷 Camera: {camera_now}")
            
            if state_changed:
                mic_active = mic_now
                camera_active = camera_now
                
                should_be_on = mic_active or camera_active
                
                print(f"🎤 Mic: {mic_active} | 📷 Camera: {camera_active}")
                loop.run_until_complete(update_plug_state(should_be_on))
            
            time.sleep(1)
            
        except Exception as e:
            print(f"Monitoring error: {e}")
            time.sleep(5)

@app.on_event("startup")
async def startup_event():
    """Start device monitoring when app starts"""
    global etw_thread
    
    etw_thread = threading.Thread(target=monitor_devices, daemon=True)
    etw_thread.start()
    print("✅ Status Light API started with ETW monitoring")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop device monitoring when app shuts down"""
    print("🛑 Status Light API shutting down")

@app.get("/status")
async def get_status():
    """Get current mic/camera/plug status"""
    return {
        "mic_active": mic_active,
        "camera_active": camera_active,
        "monitoring": True
    }

@app.post("/on-air")
async def update_status(request: Request):
    data = await request.json()
    state = data.get("Availability", "").lower()

    plug = await Discover.discover_single(PLUG_IP)
    await plug.update()
    print("state:", state)

    if state in ["busy", "inameeting", "donotdisturb"]:
        if not plug.is_on:
            await plug.turn_on()
        return {"status": "plug_on"}

    if state in ["available", "away", "offline"]:
        if plug.is_on:
            await plug.turn_off()
        return {"status": "plug_off"}

    return {"status": f"ignored_state: {state}"}