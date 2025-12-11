import asyncio
from etw import ETW, EventCallback
from kasa import SmartPlug

PLUG_IP = "192.168.1.52"

camera_active = False
mic_active = False

async def update_plug():
    plug = SmartPlug(PLUG_IP)
    await plug.update()
    should_be_on = camera_active or mic_active

    if should_be_on and not plug.is_on:
        print("🔴 ON AIR - Turning ON plug")
        await plug.turn_on()

    if not should_be_on and plug.is_on:
        print("⚫ OFF AIR - Turning OFF plug")
        await plug.turn_off()


def privacy_event_callback(event):
    global camera_active, mic_active
    event_name = event.event_name.lower()

    if "microphone" in event_name:
        if "start" in event_name:
            mic_active = True
        elif "stop" in event_name:
            mic_active = False
        print("🎤 Mic active:", mic_active)

    if "webcam" in event_name or "camera" in event_name:
        if "start" in event_name:
            camera_active = True
        elif "stop" in event_name:
            camera_active = False
        print("📷 Camera active:", camera_active)

    asyncio.run(update_plug())


def start_etw_listener():
    print("📡 Starting ETW listener for camera/mic events...")
    provider = "Microsoft-Windows-Privacy-Auditing"

    etw = ETW(
        providers=[provider],
        event_callback=privacy_event_callback
    )

    etw.start()  # Blocking loop – run in its own thread


if __name__ == "__main__":
    start_etw_listener()