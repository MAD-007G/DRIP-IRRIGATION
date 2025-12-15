import serial
import time
import threading
import json
import queue
from datetime import datetime
import paho.mqtt.client as mqtt

# =========================================================
# CONFIG
# =========================================================
PORT = "COM22"
BAUD = 9600
SLAVES = [1, 2]               # Slave IDs
PER_SLAVE_TIMEOUT = 3.0      # seconds (daisy-chain safe)
POLL_INTERVAL = 10            # seconds

# =========================================================
# SERIAL
# =========================================================
ser = serial.Serial(PORT, BAUD, timeout=0.1)
time.sleep(2)

# =========================================================
# MQTT
# =========================================================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_CMD = "irrigation/cmd"
TOPIC_MONITOR = "irrigation/monitor"

# =========================================================
# QUEUE & STATUS CACHE
# =========================================================
cmd_queue = queue.Queue()
status_cache = {}
status_lock = threading.Lock()

# =========================================================
# SERIAL SENDER (SINGLE TX PATH)
# =========================================================
def serial_sender():
    while True:
        cmd = cmd_queue.get()
        ser.write((cmd + "\n").encode())
        time.sleep(0.3)   # critical for RS485 + daisy-chain
        cmd_queue.task_done()

# =========================================================
# SERIAL RECEIVER (BUFFERED + FILTERED)
# =========================================================
def serial_receiver():
    buffer = ""

    while True:
        data = ser.read(64).decode(errors="ignore")
        if not data:
            continue

        buffer += data

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()

            # ---- FRAME VALIDATION ----
            if not line:
                continue
            if not line[0].isdigit():
                continue
            if ":" not in line:
                continue

            process_line(line)

# =========================================================
# PROCESS VALID FRAMES
# =========================================================
def process_line(line):
    parts = line.split(":")
    sid = parts[0]

    if len(parts) >= 3 and parts[1] == "STATUS":
        pico_data = {}

        for r in parts[2].split(","):
            try:
                k, v = r.split("=")
                pico_data[k] = int(v)
            except:
                continue

        with status_lock:
            status_cache[sid] = pico_data

# =========================================================
# MQTT CALLBACK (COMMAND INPUT)
# =========================================================
def on_mqtt_msg(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        sid = data["id"]

        if data["cmd"] == "STATUS":
            cmd_queue.put(f"{sid}:STATUS")
        else:
            # relay command
            cmd_queue.put(f"{sid}:{data['cmd']}:{data['state']}")

            # force immediate fresh status
            time.sleep(0.2)
            cmd_queue.put(f"{sid}:STATUS")

    except Exception as e:
        print("MQTT CMD ERROR:", e)

# =========================================================
# EVENT-BASED STATUS POLLER (CRITICAL FIX)
# =========================================================
def poll_status():
    while True:
        time.sleep(POLL_INTERVAL)

        # clear old data
        with status_lock:
            status_cache.clear()

        # request + wait PER SLAVE
        for sid in SLAVES:
            cmd_queue.put(f"{sid}:STATUS")

            start = time.time()
            while True:
                with status_lock:
                    if str(sid) in status_cache:
                        break

                if time.time() - start > PER_SLAVE_TIMEOUT:
                    break

                time.sleep(0.05)

        publish_all_status()

# =========================================================
# MQTT PUBLISH (ALL PICOS IN ONE MESSAGE)
# =========================================================
def publish_all_status():
    with status_lock:
        payload = {
            "ts": datetime.utcnow().isoformat(),
            "picos": status_cache.copy(),
            "missing": [sid for sid in SLAVES if str(sid) not in status_cache]
        }

    mqtt_client.publish(TOPIC_MONITOR, json.dumps(payload))

# =========================================================
# MQTT INIT
# =========================================================
mqtt_client = mqtt.Client()
mqtt_client.on_message = on_mqtt_msg
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.subscribe(TOPIC_CMD)
mqtt_client.loop_start()

print("[MASTER] MQTT CONNECTED")

# =========================================================
# THREADS
# =========================================================
threading.Thread(target=serial_sender, daemon=True).start()
threading.Thread(target=serial_receiver, daemon=True).start()
threading.Thread(target=poll_status, daemon=True).start()

# =========================================================
# MAIN
# =========================================================
while True:
    time.sleep(1)
