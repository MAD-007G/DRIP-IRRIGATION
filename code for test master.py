code for test  master 



import serial
import time

PORT = "COM22"     # change if needed
BAUD = 9600

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)

print("[MASTER] Ready")

def send(cmd):
    ser.write((cmd + "\n").encode())
    time.sleep(0.2)
    rx = ser.read_all().decode(errors="ignore")
    print("RX:", rx if rx else "(no response)")

while True:
    cmd = input("cmd> ")
    if cmd.lower() == "exit":
        break
    send(cmd)

ser.close()





code for s1     


from machine import UART, Pin
import time

SLAVE_ID = 1

# RS485 direction control
de_re = Pin(15, Pin.OUT)
de_re.value(0)

# UART0 -> RS485 (PC)
uart_pc = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))

# UART1 -> Next Pico
uart_next = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))

def rs485_send(data):
    de_re.value(1)
    time.sleep_us(50)
    uart_pc.write(data)
    uart_pc.flush()
    time.sleep_us(50)
    de_re.value(0)

print("Slave-1 READY")

while True:

    # ----- FROM PC -----
    if uart_pc.any():
        msg = uart_pc.readline()
        if msg:
            try:
                text = msg.decode().strip()
                target, cmd = text.split(":", 1)
                target = int(target)
            except:
                continue

            if target == SLAVE_ID:
                reply = f"{SLAVE_ID}:OK:{cmd}\n"
                rs485_send(reply.encode())
            else:
                uart_next.write(msg)

    # ----- FROM NEXT SLAVE -----
    if uart_next.any():
        data = uart_next.readline()
        if data:
            rs485_send(data)

    time.sleep(0.01)





code for s2


from machine import UART, Pin
import time

SLAVE_ID = 2   # change for each Pico

# UART0 -> from previous Pico
uart_prev = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))

# UART1 -> to next Pico
uart_next = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))

print(f"Slave-{SLAVE_ID} READY")

while True:

    if uart_prev.any():
        msg = uart_prev.readline()
        if msg:
            try:
                text = msg.decode().strip()
                target, cmd = text.split(":", 1)
                target = int(target)
            except:
                continue

            if target == SLAVE_ID:
                reply = f"{SLAVE_ID}:OK:{cmd}\n"
                uart_prev.write(reply.encode())
            else:
                uart_next.write(msg)

    time.sleep(0.01)

