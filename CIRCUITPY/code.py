import time
import board
import busio
from analogio import AnalogIn
from digitalio import DigitalInOut, Direction, Pull

from adafruit_espatcontrol import adafruit_espatcontrol, adafruit_espatcontrol_wifimanager

# Get wifi details and more from a settings.py file
try:
    from secrets import wifi_settings, server_ip
except ImportError:
    print("WiFi settings & server IP are kept in secrets.py, please add them there!")
    raise


# Setting up photo diode and leds
photodiode = AnalogIn(board.A2)
white_led = DigitalInOut(board.D3)
white_led.direction = Direction.OUTPUT
blue_led = DigitalInOut(board.RGB_LED_BLUE)
blue_led.direction = Direction.OUTPUT

# Setting up switch as digital input
switch = DigitalInOut(board.D5)
switch.direction = Direction.INPUT
switch.pull = Pull.UP

# Setting up Particle Argon
RX = board.ESP_TX
TX = board.ESP_RX
resetpin = DigitalInOut(board.ESP_WIFI_EN)
rtspin = DigitalInOut(board.ESP_CTS)
uart = busio.UART(TX, RX, timeout=0.1)
esp_boot = DigitalInOut(board.ESP_BOOT_MODE)
esp_boot.direction = Direction.OUTPUT
esp_boot.value = True

# Contant definition

# Use 1000 to make it less sensitive to changes:
LIGHT_THRESHOLD = 900
# Waiting period *without* laser hitting the photodiode before triggering signal:
WAIT_PERIOD = 0.5 #secs

# Payload needed by webhooks plugin for Homebridge 
DATA = 'http://{}/?accessoryId=laser1&state='.format(server_ip)
TRIGGER_TRUE = DATA+'true'
TRIGGER_FALSE = DATA+'false'


print("ESP AT commands")
esp = adafruit_espatcontrol.ESP_ATcontrol(uart, 115200,
                                          reset_pin=resetpin, rts_pin=rtspin, debug=False)
wifi = adafruit_espatcontrol_wifimanager.ESPAT_WiFiManager(esp, wifi_settings)

print("Resetting ESP module")
esp.hard_reset()

first_pass = True
counter_started = False
trigger_time = 0.0
armed = False

def blink(times):
    '''
    Blinks white led as many times as the passed argument.
    '''
    
    for b in range(times):

        white_led.value = False
        time.sleep(0.1)
        white_led.value = True
        time.sleep(0.2)
        white_led.value = False
        time.sleep(0.1)

def adjust_mode():
    '''
    Setting the device to this mode allows for the laser beam
    to be adjusted to point to the photodiode without sending 
    an alarm signal/request to the server. In this mode, the white LED
    is turned on when the laser beam hits the photodiode.
    '''

    print('Adjust mode...')
    if photodiode.value >= LIGHT_THRESHOLD:
        white_led.value = True
    else:
        white_led.value = False

def detect_mode():
    '''
    Setting the device to this mode makes it send an alarm signal/request 
    to the server whenever the laser beam is interrupted a predefined 
    number of seconds (WAIT_PERIOD).
    '''

    global trigger_time, WAIT_PERIOD, counter_started

    print('Detect mode...')
    current_time = time.monotonic()
    if current_time - trigger_time >= WAIT_PERIOD and counter_started:
            
        print('Threshold reached!. Sending update signal to server...')
        white_led.value = True
        response = wifi.get(TRIGGER_TRUE)
        print(response.json())
        #time.sleep(2)
        print('Sending release signal to server..')
        response = wifi.get(TRIGGER_FALSE)
        white_led.value = False
        counter_started = False
            
    if photodiode.value < LIGHT_THRESHOLD and not counter_started:
        trigger_time = time.monotonic()
        counter_started = True

    if photodiode.value >= LIGHT_THRESHOLD and counter_started:
        # Resets counter if light value falls below light threshold
        # before finishing the waiting period:
        counter_started = False
        

while True:

    try:

        # Just prints available access points on first pass:
        if first_pass :
            print("Scanning for AP's")
            for ap in esp.scan_APs():
                print(ap)
            first_pass = False
            print("Checking connection...")
            
        while not esp.is_connected:
            # Turns on blue LED:
            blue_led.value = False 
            print("Connecting...")
            esp.connect(wifi_settings)
            print("Connected to AT software version ", esp.version)
            
        #Turns of LED
        blue_led.value = True
        print('photodiode value: {}'.format(photodiode.value))

        if not armed:
            adjust_mode()
        else:
            detect_mode()

        # Button pressed:
        if not switch.value:
            print('switch pressed.')
            # Toggles mode flag value:
            armed = not armed

            if armed:
                blink(4)
            else:
                blink(2)


    # Error handling needed below as ESP AT commands may be a bit
    # unreliable.
    except (ValueError,RuntimeError, adafruit_espatcontrol.OKError) as e:
        print("Failed to get data, retrying\n", e)
        print("Resetting ESP module")
        esp.hard_reset()
        continue