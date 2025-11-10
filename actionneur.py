import keyboard

VOLUME_UP = 115
def do():
    print("Button was pressed")

print("start")
while True:
    ev = keyboard.read_event()
    print(f"Button press : {ev}")
    if ev.scan_code == VOLUME_UP and ev.event_type == keyboard.KEY_DOWN:
        do()