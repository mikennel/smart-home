from fastapi import FastAPI, Request
import asyncio
from kasa import Discover
import threading
import winreg
import time

app = FastAPI()

# Configuration 
PLUG_NAME = "On Air Sign"  # Change this to match your plug's name in the Kasa app - HS103
PLUG_IP = None  # Will be auto-discovered

# Global state
mic_active = False
camera_active = False
etw_thread = None
discovered_plug = None


async def find_plug_by_name(target_name: str):
    """Discover plug on network by its alias/name"""
    print(f"[INFO] Searching for plug named '{target_name}'...")
    try:
        devices = await Discover.discover()
        for ip, device in devices.items():
            await device.update()
            if device.alias.lower() == target_name.lower():
                print(f"[SUCCESS] Found '{device.alias}' at {ip}")
                return device, ip
        print(f"[WARNING] Plug '{target_name}' not found on network")
    except Exception as e:
        print(f"[ERROR] Discovery error: {e}")
    return None, None


async def get_plug():
    """Get the plug, using cached instance or discovering by name"""
    global discovered_plug, PLUG_IP
    
    # If we have IP, try direct connection first (faster)
    if PLUG_IP:
        try:
            plug = await Discover.discover_single(PLUG_IP)
            await plug.update()
            return plug
        except:
            # IP failed, clear it and rediscover
            print(f"[WARNING] Plug not responding at {PLUG_IP}, rediscovering...")
            PLUG_IP = None
    
    # Discover by name
    plug, ip = await find_plug_by_name(PLUG_NAME)
    if plug:
        PLUG_IP = ip  # Cache the IP for faster access next time
        discovered_plug = plug
    return plug


async def update_plug_state(should_be_on: bool):
    """Update the plug state based on mic/camera status"""
    try:
        plug = await get_plug()
        if not plug:
            print("[ERROR] Plug not available")
            return
        
        await plug.update()
        
        if should_be_on and not plug.is_on:
            await plug.turn_on()
            print("[ON AIR] Plug turned ON")
        elif not should_be_on and plug.is_on:
            await plug.turn_off()
            print("[OFF AIR] Plug turned OFF")
    except Exception as e:
        print(f"[ERROR] Error updating plug: {e}")


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
                                    # print(f"  {device_type} in use by: {subkey_name.split('#')[-1]}")
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
    
    print("[INFO] Device monitoring started")
    
    while True:
        try:
            camera_now, mic_now = check_camera_mic()
            
            state_changed = (mic_now != mic_active) or (camera_now != camera_active)
            
            if state_changed:
                mic_active = mic_now
                camera_active = camera_now
                
                should_be_on = mic_active or camera_active
                
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
    print("[SUCCESS] Status Light API started with device monitoring")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop device monitoring when app shuts down"""
    print("[INFO] Status Light API shutting down")

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

    if state in ["on", "busy", "inameeting", "donotdisturb"]:
        if not plug.is_on:
            await plug.turn_on()
        return {"status": "plug_on"}

    if state in ["available", "away", "offline"]:
        if plug.is_on:
            await plug.turn_off()
        return {"status": "plug_off"}

    return {"status": f"ignored_state: {state}"}