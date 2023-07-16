"""
Crossley Gate Monitor
Written by Jared Crossley, 2023, for ESP32 (MicroPython)
--
This script monitors the input from an optocoupler connected to the LED output of a Centurion D5 (2008) gate motor. In more detail, this script:
- Reads the status of the LED every tenth of a second (i.e. every 0.1 seconds), incrementing a count if the LED is illuminated
- Interprets the length of time that the LED has been illuminated every 5 seconds
- Correlates the length of time that the LED has been illuminated against an array of statuses
- Sends a notification through Pushover if warranted by the current status

"""

# import libraries
import time
import network
import urequests
from machine import Pin
import _thread
# import configuration script
import config

# configuration

# -- network
wifi_ssid = config.wifi_ssid
wifi_password = config.wifi_password

# -- pushover
pushover_url = "https://api.pushover.net/1/messages.json"
pushover_user = config.pushover_user
pushover_app_token = config.pushover_app_token

# -- gpio
# set input to GPIO pin 25
# enable the built-in PULL DOWN resistor to pull the pin DOWN (0) prevent noise that might result in false HIGH (1) readings
gate_input_gpio_pin = Pin(25, Pin.IN, Pin.PULL_DOWN)

# -- do not change
# onboard LED
onboard_led = Pin(2, Pin.OUT)

def led_status_flash(num_flashes):
	"""
	Flashes the onboard LED to indicate a task is in progress.
	The LED will flash at a rate of five flashes per second (i.e. 0.2 s on, 0.2 s off)

	Parameters
	----------
	num_flashes:	int, required
		The number of times to flash the LED.
	"""
	for i in range(num_flashes):
		time.sleep(0.2)
		onboard_led.on()
		time.sleep(0.2)
		onboard_led.off()

def connect_wifi(ssid = wifi_ssid, password = wifi_password):
	"""
	Connects to a WiFi network

	Parameters
	----------
	ssid:		string, required
		The WiFi network name.
	password:	string, required
		The WiFi network password.
	"""
	wlan = network.WLAN(network.STA_IF)
	wlan.active(True)
	if not wlan.isconnected():
		print("Connecting to WiFi...")
		# flash the onboard LED four times to indicate connecting to WiFi
		led_status_flash(4)
		wlan.connect(ssid, password)
		while not wlan.isconnected():
			pass
		# flash the onboard LED two times to indicate connection was successful
		led_status_flash(2)
		print("WiFi connected. Network config:", wlan.ifconfig())

def notify(message, url = pushover_url, app_token = pushover_app_token, user = pushover_user, title = "", sound = "pushover"):
	"""
	Sends a notification to Pushover

	Parameters
	----------
	message:	string, required
		The message to send via Pushover.
	url:		string, required
		The Pushover URL to which the message should be sent.
	app_token:	string, required
		The Pushover app token.
	user:		string, required
		The Pushover user.
	title:		string, optional
		The title to give the message via Pushover. Defaults to blank.
	sound:		string, optional
		The sound to play with the message via Pushover. See https://pushover.net/api#sounds. Defaults to "pushover".
	"""
	print("Sending pushover notification...")
	# flash the onboard LED three times to indicate sending notification
	led_status_flash(3)
	# set the request payload
	payload = "?message=" + message + "&token=" + app_token + "&user=" + user + "&title=" + title + "&sound=" + sound
	url += payload
	
	# make the request to Pushover
	r = urequests.post(url, headers = {"user_agent": "crossley_gate"})
	# close the request to prevent running out of memory
	r.close()

def read_gate():
	"""
	Reads and interprets the gate status.

	Parameters
	----------
	None.
	"""

	# gate status variables - these are all related
	# -> initial gate status
	gate_status = 0 # default is 0 (gate closed)
	# -> gate status options
	# 0 = default (gate closed)
	# 1 = opening/open/closing
	# 2 = ac power or battery failure
	gate_status_options = [0,1,2]
	# -> gate status strings
	# these tie up with the value of *gate_status_options*
	gate_status_string = ["Gate closed", "Gate OPEN", "Gate has an AC power or battery failure"]
	# -> gate gtatus strings - when repeated
	# if a gate status is repeated, what should the notification say?
	gate_status_string_repeat = ["Gate closed", "Gate still OPEN", "Gate has an AC power or battery failure"]
	# -> gate status time
	# the duration, in seconds, that the LED must be on within 5 seconds to trigger a status. [greater or equal to this value, less than or equal to this value]
	gate_status_time = [[0,0],[2,6],[0.5,1.5]]
	# -> gate status notifications
	# should a notification be sent for a particular gate status? 0 for no, 1 for yes.
	gate_status_report = [0,1,1]
	# -> gate status wait
	# how long should the script wait (in seconds) before resending a notification if the gate status has not changed?
	gate_status_wait = [0,300,1800]
	# -> gate status confirm
	# should the script confirm a particular status before changing to it? This is to prevent nuisance statuses. 0 for no, 1 for yes.
	gate_status_confirm = [1,0,1]
	# initialise a variable to store whether a status to be confirmed has been received.
	gate_status_tobeconfirmed = -1
	# -> gate status last update
	# initialise the variable to store when a notification of the gate status was last sent.
	gate_status_lastupdate = time.time() # initialise our last update as having occured now (the actual time does not matter)
    
	# start an infite loop
	while True:
		# listen for 5 seconds
		time_count = 0 # keep track of how long the script has been listening
		led_on_count = 0 # keep track of how long the gate LED has been on for
		new_gate_status = 0 # a temporary variable to be updated below
		while time_count < 5:
			# is the LED illuminated?
			if gate_input_gpio_pin.value(): # true, LED is illuminated
				# illuminate onboard LED
				onboard_led.on()
				# to prevent false readings, force a restart of time_count if the LED is illuminated, led_on_count = 0, but time_count is greater than 0
				if time_count > 0 and led_on_count == 0:
					time_count = -0.1
					print("Restarting count to confirm LED is on.")
				else:
					# LED is illuminated, led_on_count > 0, and time_count > 0
					led_on_count += 0.1 # increment *led_on_count* by 0.1 seconds
					# debug: print("LED is on and has been on for " + str(led_on_count) + " seconds")
			else:
				# extinguish onboard LED
				onboard_led.off()
			time_count += 0.1 # increment *time_count* by 0.1 seconds
			time.sleep(0.1) # pause the script for a tenth of a second (0.1 seconds)
		# after 5 seconds, process the data and determine the current status of the gate
		for x in range(0,len(gate_status_options)):
			if led_on_count >= gate_status_time[x][0] and led_on_count <= gate_status_time[x][1]:
				new_gate_status = gate_status_options[x]
		# has gate status changed?
		if new_gate_status == gate_status:
			# gate status has not changed.
			print("Gate Status has not changed.")
			print("Gate Status is: " + gate_status_string[new_gate_status])
			# are notifications sent for this gate status?
			if (gate_status_report[new_gate_status]):
				# yes, but has sufficient time elapsed since the previous notification?
				# take the last update time and add waiting time to it
				time_compare = gate_status_lastupdate + gate_status_wait[new_gate_status]
				# take the time now
				# determine the difference (in seconds) between the time now and the comparison time
				time_difference = (time.time() - time_compare)
				# if the difference is less than 0, then we're not ready to send a notification. If greater, then send a notification.
				if time_difference >= 0:
					# yes, enough time has passed since the previous notification. Send another notification.
					print("Send Notification: " + gate_status_string_repeat[new_gate_status])
					notify(gate_status_string_repeat[new_gate_status])
					# update *gate_status_lastupdate*
					gate_status_lastupdate = time.time()
		else:
			# gate status has changed
			print("Gate Status has changed.")
			print("Gate Status is now: " + gate_status_string[new_gate_status])
			# does the gate status need to be confirmed?
			if gate_status_confirm[new_gate_status]:
				# yes, but is this the confirmation?
				if gate_status_tobeconfirmed == new_gate_status:
					# yes, this is the second time in a row that we are receiving this status. Update the gate status.
					print("Gate Status Confirmed.")
					# update *gate_status*
					gate_status = new_gate_status
					# update *gate_status_lastupdate*
					gate_status_lastupdate = time.time()
					# are notifications sent for this gate status?
					if (gate_status_report[new_gate_status]):
						# Yes, send a notification
						print("Send Notification: " + gate_status_string[new_gate_status])
						notify(gate_status_string[new_gate_status])
					# reset *gate_status_tobeconfirmed*
					gate_status_tobeconfirmed = -1
				else:
					# no, we must confirm the gate status before changing to it.
					print("Gate Status must be confirmed.")
					gate_status_tobeconfirmed = new_gate_status
			else:
				# no, the gate status does not need to be confirmed.
				# update *gate_status*
				gate_status = new_gate_status
				# update *gate_status_lastupdate*
				gate_status_lastupdate = time.time()
				# are notifications sent for this gate status?
				if (gate_status_report[new_gate_status]):
					# yes, send a notification
					print("Send Notification: " + gate_status_string[new_gate_status])
					notify(gate_status_string[new_gate_status])
					gate_status_tobeconfirmed = -1

# run the script
while True:
	print("~~~ CROSSLEY GATE STATUS NOTIFIER (FOR ESP32) ~~~")
	# connect to the WiFi network
	print("Connect to WiFi...")
	connect_wifi()
	# run the gate status interpreter
	print("Begin reading gate status...")
	read_gate()