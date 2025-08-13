import subprocess
import sqlite3
import os
import uuid
import netifaces as ni
import time
from paho.mqtt import client as mqtt_client
import random
import json


#           sensorConfiguration.py
#
#   This script allows to setup all sensor configurations
#   configurations by running only this script.
#
#
#   The configurations are divided in three
#   different parts:
#   (1) Sensor General Configuration; -> Configuration of (Sensor UUID, Sensor Name, Sensor Location, Status, Power Filtration)
#   (2) Sensor Upload Configuration; -> Configuration of InfluxDB upload parameters (Cloud Server IP Address, Org Name, Bucket Name, Authorization token) 
#   (3) Sensor Tasks Configuration. -> Configuration of cronjobs for automatic time-scheduling tasks.
#
#   Author: Tomas Mestre Santos
#   Date: 08-02-2024
#


# Filepath of python script for sending crowding data to InfluxDB
SENSOR_SEND_CROWDING_DATA_FILEPATH = "/home/kali/Desktop/sendCrowdingData.py"

# Filepath for python script for sending sensor location to InfluxDB
SENSOR_SEND_LOCATION_FILEPATH = "/home/kali/Desktop/sendSensorLocation.py"

# Filepath of python script for changing upload technology 
SENSOR_COMMUNICATION_CHECK_FILEPATH = "/home/kali/Desktop/sensorCommunicationCheck.py"

#Filepath to cronjobs output text file
DEFAULT_CRONJOBS_FILEPATH = "/home/kali/Desktop/cronjobs_default.txt"
CONFIGURED_CRONJOBS_FILEPATH = "/home/kali/Desktop/cronjobs_configured.txt"

# Filepath of airodump-ng.c detection software
AIRODUMP_FILEPATH = "/home/kali/Desktop/aircrack-ng-1.7/src/airodump-ng/airodump-ng.c"

#MQTT Paramenters
MQTT_PORT = 1883
MQTT_USERNAME = 'tmmss1'
MQTT_PASSWORD = 'tomasantos00'


#Number of configuration parameters (uuid, name, etc...)
SENSOR_CONFIG_PARAMETERS_NUMB = 15
DEFAULT_CONFIG_PARAMETERS_NUMB = 12

#Raspberry Pi OUIs List
rpi_oui = ["dc:a6:32", "b8:27:eb", "28:cd:c1", "2c:cf:67", "3a:35:41", "d8:3a:dd", "e4:5f:01"]


#Auxiliary functions

def valid_latlon(lat: float, lon: float):
    try:
        float(lat), float(lon)

        if (float(lat) >= -90 and float(lat) <= 90) and (float(lon) >= -180 and float(lon) < 180):
            return True
        else:
            return False    
        
    except ValueError:
        return False 

def valid_sensor_name(name):
    valid_name = True

    if name.strip() == '':
        print("Sensor name is empty.")
        valid_name = False
    else:
        for c in name:
            if not c.isalnum():
                valid_name = False
                print("Sensor name can only contain alphanumeric characters (alphabet letters and numbers).")
                break

    return valid_name

def validate_IP_address(ipAddress):

    valid_IP = True
 
    for i in ipAddress:

        if i.isalpha():
            print("The IP address should only contain numbers.")
            valid_IP = False
            break

    if valid_IP: 
        dot_count = 0

        for i in ipAddress:

            if i == ".":
                dot_count += 1

        if dot_count != 3:
            print("The IP address is not in the correct syntax.")
            valid_IP = False

        if valid_IP:

            ip_list = list(map(str, ipAddress.split('.')))  
        
            for element in ip_list:  
                if element=='' or (int(element) < 0 or int(element) > 255 or (element[0]=='0' and len(element)!=1)):  
                    print("The IP address is not in the correct syntax.")
                    valid_IP = False
                    break
    
    return valid_IP

def heliumNodeSetup():
    #for your first session after boot, you will need to do a hard-reset instead of a reset lora command to activate the module
    #cmd = "sudo rak811 hard-reset"
    #os.system(cmd)

    cmd = "sudo rak811 -v reset lora"
    os.system(cmd)

    cmd = "sudo rak811 -v set-config app_eui=190E110342012981 app_key=CBDF9117D3E1A7F9AA11166ED97BF8F6"
    os.system(cmd)

    cmd = "sudo rak811 -v dr 2"
    os.system(cmd)

    cmd = "sudo rak811 -v join-otaa"
    output = subprocess.check_output(cmd, shell=True)

    if "Joined in OTAA mode" in str(output):
        print("Connected to Helium network.")
        set_lora_connected(True)
        return True
    else:
        print("Not connected to Helium network.")
        set_lora_connected(False)
        return False
    
def connect_mqtt():
    client_id = f'python-mqtt-{random.randint(0, 1000)}'

    #Get cloud ip address
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        cloud_ip_addr = cwifi.execute("""SELECT Cloud_IP_Address FROM SensorConfiguration""").fetchone()[0]

        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to get data from database.", error)

    def on_connect(client, userdata, flags, rc, properties):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)
            
    # Set Connecting Client ID
    client = mqtt_client.Client(client_id=client_id, callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.connect(cloud_ip_addr, MQTT_PORT) 
    return client


#Configuration prompts functions
def fast_config():
    print("------------------------------------------------------------------")
    print("------               FAST CONFIGURATION MODE                ------")
    print("------------------------------------------------------------------")

    # Generate a UUID based on Raspberry Pi's hardware MAC address
    uuid_from_mac_addr = uuid.getnode()
    print("Sensor unique identifier (UUID) created: " + str(uuid_from_mac_addr))

    #Sensor Name
    sensorName = input("Sensor name: ").strip()
    while valid_sensor_name(sensorName) is False:
        sensorName = input("Sensor name: ").strip()

    upload_technology = get_upload_technology()

    upload_interface, detection_interface = check_upload_detection_interfaces(False)

    return uuid_from_mac_addr, sensorName, upload_technology, upload_interface, detection_interface

def config_general():

    print("------------------------------------------------------------------")
    print("------             SENSOR GENERAL CONFIGURATION             ------")
    print("------------------------------------------------------------------")

    # Generate a UUID based on Raspberry Pi's hardware MAC address
    uuid_from_mac_addr = uuid.getnode()
    print("Sensor unique identifier (UUID) created: " + str(uuid_from_mac_addr))

    #Sensor Name
    sensorName = input("Sensor name: ").strip()
    while valid_sensor_name(sensorName) is False:
        sensorName = input("Sensor name: ").strip()
        
    # Sensor Location(Latitude, Longitude)
    latitude, longitude = (10000, 0)   # Initial invalid coordinates on purpose
    while valid_latlon(latitude, longitude) is False:

        lat, lon = input("Sensor location (latitude, longitude) separeted by commas [E.g.: (31.66, -9.34)]: ").split(",")

        latitude = lat.strip()
        longitude = lon.strip()

        if latitude == '' or longitude == '':
            print("Not enought values. 2 arguments expected, 1 inserted. Please try again.")
        else:
            if valid_latlon(latitude.strip(), longitude.strip()) is False:
                print("Invalid coordinates. Please try again.")

    # Status ('Active' or 'Disabled')
    status = ''
    while status not in ('Active', 'Disabled'):
        status = input("Status ('Active' or 'Disabled'): ").strip()

        if status not in ('Active', 'Disabled'):
            print("\tPlease enter 'Active' or 'Disabled'.")

    # Power Filtration
    power_filtration = '100'  # Initial invalid power filtration on purpose
    while not (power_filtration == "0" or (int(power_filtration) >= -100 and int(power_filtration) <= 0)):
        power_filtration = input("Power Filtration [-100, 0] dB (Insert '0' to ignore): ").strip()

        if power_filtration == "0":
            print("No Power Filtration")
            power_filtration = 0

        else:

            if not power_filtration[1:].isnumeric():
                print("\tPower filtration must be a number.")
                power_filtration = '100'    # Set power filtration to a number on purpose
                                
            elif power_filtration[0] == "-":
                if not (int(power_filtration) >= -100 and int(power_filtration) <= 0):
                    print("\tPower filtration must be between [-100, 0] dB.")
            else:
                print("\tPower filtration must be between [-100, 0] dB.")
                power_filtration = '100'    # Set power filtration to a number on purpose



    return uuid_from_mac_addr, sensorName, latitude, longitude, status, power_filtration

def config_influx():

    print("------------------------------------------------------------------")
    print("------             SENSOR UPLOAD CONFIGURATION              ------")
    print("------------------------------------------------------------------")

    cloudServerIPAddress = input("Cloud Server IP Address: ").strip()
    while validate_IP_address(cloudServerIPAddress) is not True:
        cloudServerIPAddress = input("Cloud Server IP Address: ").strip()
    influxDB_Org_Name = input("InfluxDB Organization name: ").strip()
    influxDB_Bucket = input("InfluxDB Bucket name: ").strip()
    authorization_Token = input("Authorization token: ").strip()


    return cloudServerIPAddress, influxDB_Org_Name, influxDB_Bucket, authorization_Token

def config_tasks():

    print("------------------------------------------------------------------")
    print("------               SENSOR TAKS CONFIGURATION              ------")
    print("------------------------------------------------------------------")

    uploadInterface, detectionInterface = check_upload_detection_interfaces(False)

    # Cron jobs configuration
    print("TASKS CONFIGURATION:")

    # Periodic upload of crowding data to the Cloud Server
    print("(1) Periodic upload of crowding data to the Cloud Server:")

    uploadPeriodicity = ''
    while not (uploadPeriodicity.isdigit() and (int(uploadPeriodicity) > 0 and int(uploadPeriodicity) < 60 )):

        uploadPeriodicity = input("\tUpload periodicity of messages (in minutes [1-59]): ").strip()

        if not uploadPeriodicity.isdigit():
            print("\tPeriodicity must be a number.")
        elif uploadPeriodicity.isdigit() and not (int(uploadPeriodicity) > 0 and int(uploadPeriodicity) < 60):
            print("\tPeriodicity must be between 1 and 59.")

    slidingWindow =''
    while not (slidingWindow.isdigit() and (int(slidingWindow) > 0 and int(slidingWindow) < 60)):

        slidingWindow = input("\tSliding window time (in minutes [1-59]): ").strip()

        if not slidingWindow.isdigit():
            print("\tSliding window must be a number.")
        elif slidingWindow.isdigit() and not (int(slidingWindow) > 0 and int(slidingWindow) < 60):
            print("\tSliding window must be between 1 and 59.")

    # Upload Technology
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        sensor_communication = cwifi.execute("""SELECT WifiAvailable, LoRaAvailable, WifiConnected, LoRaConnected FROM SensorCommunication""").fetchone()

        wifiAvailable = sensor_communication[0]
        loraAvailable = sensor_communication[1]
        wifiConnected = sensor_communication[2]
        loraConnected = sensor_communication[3]

        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to read data from database.", error)

    if wifiAvailable and wifiConnected:
        technology = 'wifi'
    elif loraAvailable and loraConnected:
        technology = 'lora'

    print(f"Upload technology '{technology}' automatically selected for data communication.")
    time.sleep(1)

    # Periodic delete of outdated and unnecessary data from local database
    '''
    print("(4) Periodic delete of outdated and unnecessary data: ")
    retentionPeriodicity = ''
    while not (retentionPeriodicity.isdigit() and (int(retentionPeriodicity) > 0 and int(retentionPeriodicity) < 24)):

        retention = input("\tRetention periodicity (in hours [1-23]): ").strip()

        if not retentionPeriodicity.isdigit():
            print("\tRetention periodicity must be a number.")
        elif retentionPeriodicity.isdigit() and not (int(retentionPeriodicity) > 0 and int(retentionPeriodicity) < 24):
            print("\tRetention periodicity must be between 1 and 23.")

    retentionPolicy = ''
    while not (retentionPolicy.isdigit() and (int(retentionPolicy) > 0 and int(retentionPolicy) < 60)):

        retentionPolicy = input("\tRetention policy (in minutes [1-59]): ").strip()

        if not retentionPolicy.isdigit():
            print("\tRetention policy must be a number.")
        elif retentionPolicy.isdigit() and not (int(retentionPolicy) > 0 and int(retentionPolicy) < 60):
            print("\tRetention policy must be between 1 and 59.")
    '''
    print("(2) Task for periodic delete of outdated and unnecessary data created.")
    time.sleep(1)

    # Weekly upload of OUI list
    print("(3) Task for Weekly upload of OUI list created.")
    time.sleep(1)

    # Daily reboot
    print("(4) Reboot:")
    print("\tReboot Periodicity: ")
    print("\t  0 - Daily")
    print("\t  1 - Every two days")
    print("\t  2 - Every three days")
    print("\t  3 - Weekly")
    print("\t  4 - Monthly")
    print("\t  5 - No Reboot")
    rebootPeriodicity = input("\tReboot Periodicity [0-5]: ").strip()
    while not (rebootPeriodicity.isdigit() and (int(rebootPeriodicity) >= 0 and int(rebootPeriodicity) < 6)) :
        rebootPeriodicity = input("\tReboot Periodicity [0-5]: ").strip()

        if not rebootPeriodicity.isdigit():
            print("\tPlease choose a number.")
        elif rebootPeriodicity.isdigit() and not (int(rebootPeriodicity) >= 0 and int(rebootPeriodicity) < 6):
            print("\tPlease enter a number between 0 and 5.")

    if   rebootPeriodicity == "0": rebootPeriodicity = 'daily'
    elif rebootPeriodicity == "1": rebootPeriodicity = 'everytwodays'
    elif rebootPeriodicity == "2": rebootPeriodicity = 'everythreedays'
    elif rebootPeriodicity == "3": rebootPeriodicity = 'weekly'
    elif rebootPeriodicity == "4": rebootPeriodicity = 'monthly'
    elif rebootPeriodicity == "5": rebootPeriodicity = 'noreboot'

    if rebootPeriodicity != 'noreboot':
        rebootTime = input("\tSensor reboot hour [0-23]: ").strip()
        while not (rebootTime.isdigit() and (int(rebootTime) >= 0 and int(rebootTime) < 24)) :
            rebootTime = input("\tSensor reboot hour [0-23]: ").strip()

            if not rebootTime.isdigit():
                print("\tReboot time must be a number.")
            elif rebootTime.isdigit() and not (int(rebootTime) >= 0 and int(rebootTime) < 24):
                print("\tPlease enter a number between 0 and 23.")
    else:
        rebootTime = 0
    print("Task for daily reboot created.")
    time.sleep(1)

    return uploadInterface,detectionInterface,uploadPeriodicity,slidingWindow,technology.lower(), rebootPeriodicity, rebootTime


#Custom-made functions
def write_crontab_file(status, detection_if, upload_periodicity, reboot_periodicity, reboot_time):
    # Write tasks configuration file        
    print("Creating new tasks configuration file...")
    f = open(CONFIGURED_CRONJOBS_FILEPATH, 'w')
    print("New configuration file created.")
    print("")

    print("Writing tasks to configuration file...")

    f.write("# This file allows users to configure the sensor tasks to be run\n")
    f.write("# automatically on pre-determined time-shedules.\n")
    f.write("#\n")
    f.write("# SENSOR CONFIGURED TASKS: \n")
    f.write("#\n")
    f.write("# Check available communication technologies and interfaces\n")
    f.write("@reboot sleep 15 && /usr/bin/python3 /home/kali/Desktop/sensorCommunicationAvailable.py\n")
    f.write("# Periodic check of communication technologies and interfaces\n")
    f.write("*/5 * * * * /usr/bin/python3 /home/kali/Desktop/sensorCommunicationCheck.py\n")
    if status == "Active":
        f.write("# Wi-Fi detection of devices\n")
        f.write("*/10 * * * * timeout -k 1 590s sudo airodump-ng --background 1 " + str(detection_if + "\n"))
        f.write("*/10 * * * * sleep 595 && sudo pkill airodump-ng\n")
        f.write("# Periodic upload of crowding data to the Cloud Server\n")
        f.write("*/" + str(upload_periodicity) + " * * * * /usr/bin/python3 /home/kali/Desktop/sendCrowdingData.py \n")
        f.write("# Periodic delete of outdated and unnecessary data from local database\n")
        f.write("0 * * * * /usr/bin/python3 /home/kali/Desktop/dataRetentionManager.py 30\n")
    elif status == "Disabled":
        f.write("# Wi-Fi detection of devices\n")
        f.write("#*/10 * * * * timeout -k 1 590s sudo airodump-ng --background 1 " + str(detection_if + "\n"))
        f.write("#*/10 * * * * sleep 595 && sudo pkill airodump-ng\n")
        f.write("# Periodic upload of crowding data to the Cloud Server\n")
        f.write("#*/" + str(upload_periodicity) + " * * * * /usr/bin/python3 /home/kali/Desktop/sendCrowdingData.py \n")
        f.write("# Periodic delete of outdated and unnecessary data from local database\n")
        f.write("#0 * * * * /usr/bin/python3 /home/kali/Desktop/dataRetentionManager.py 30\n")
    f.write("# Periodic upload of OUI list\n")
    f.write("0 0 * * 0 /usr/bin/python3 /home/kali/Desktop/macOUIupdater.py\n")
    f.write("# Reboot\n")
    if reboot_periodicity == "daily":
        f.write("0 " + str(reboot_time) + " * * * sudo reboot\n")
    elif reboot_periodicity == "everytwodays":
        f.write("0 " + str(reboot_time) + " */2 * * sudo reboot\n")
    elif reboot_periodicity == "everythreedays":
        f.write("0 " + str(reboot_time) + " */3 * * sudo reboot\n")
    elif reboot_periodicity == "weekly":
        f.write("0 " + str(reboot_time) + " * * 0 sudo reboot\n")
    elif reboot_periodicity == "monthly":
        f.write("0 " + str(reboot_time) + " 1 * * sudo reboot\n")
    elif reboot_periodicity == "noreboot":
        f.write("#0 " + str(reboot_time) + " * * * sudo reboot\n")

    f.close()

    print("Tasks configuration file sucessfully writen.")


    # Load tasks configuration file to crontab

    cmd = "crontab -u kali " + CONFIGURED_CRONJOBS_FILEPATH
    #print(cmd)
    os.system(cmd)

    print("Configuration saved sucessfully.")
        
def check_upload_detection_interfaces(start_monitor_mode:bool):
    # Selection of upload and detection interfaces
    
    #
    # NOTA: Este script assume que existirao apenas 2 interfaces wifi (wlan's) ligadas, em que 
    #       uma e a do RaspberryPi (dc:a6:32) e que a outra sera precisamente a interface do
    #       dongle de wifi externo (antenas Alfa Networks). Desta forma, deteta-se qual e a
    #       wlan correspondente a interface de detecao por exclusao de partes (se nao e a do
    #       Raspberry Pi, entao sera a outra!)
    #
    
    print("Checking network interfaces...")

    interfaces = ni.interfaces()

    upload_interface='None'

    for iface in interfaces:

        if iface == "eth0" and len(ni.ifaddresses(iface)) > 2: 
            upload_interface=iface
            break

        elif iface[:4] == "wlan":
                
                if ni.ifaddresses(iface)[ni.AF_LINK][0]['addr'][:8] in rpi_oui:
                        upload_interface=iface
                        break                


    detection_interface = None
    cmd = "sudo airmon-ng"
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8")


    lines = output.splitlines()[3:]
    lines.remove("")

    interfaces = []

    for line in lines:
        interface = line.split("\t")
        interface.remove("")
        interfaces.append(interface)

    if len(interfaces) < 2:
        print("WARNING! You do not have connected an external Wi-Fi dongle. \nPlease connect an external Wi-Fi dongle to the sensor and then run this script again.")
        print("----------------------------------------------------------------")
        
    else:

        for interface in interfaces:
            dongle_manuf = interface[-1:][0].lower()

            if "realtek" in dongle_manuf:
                start_monitor_interface = interface[1]
                detection_interface = interface[1]
                break
            
            elif "mediatek" in dongle_manuf:
                start_monitor_interface = interface[1]

                if interface[1][-3:] == "mon":
                    detection_interface = interface[1]
                    start_monitor_mode = False
                else:
                    detection_interface = interface[1] + "mon"

                break

        if start_monitor_mode == True:
            cmd = f"sudo airmon-ng start {start_monitor_interface}"
            subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("utf-8")
            print(f"Started monitor mode on interface '{start_monitor_interface}'.")
        
    if upload_interface is not None: print("Interface '" + upload_interface + "' automatically selected for uploading data.")
    if detection_interface is not None: print("Interface '" + detection_interface + "' automatically selected for detecting devices.")

    return upload_interface, detection_interface

def publish_location_mqtt_message(msg_payload, topic):
    client = connect_mqtt()

    result = client.publish(topic, msg_payload)

    # result: [0, 1]
    status = result[0]
    if status == 0:
        print(f"Send `{msg_payload}` to topic `{topic}`.")
        return True
    else:
        print("\nFailed to publish mqtt message.")
        return False

def publish_detections_mqtt_message(unix_timestamp, devices_detected: int, topic):
    client = connect_mqtt()

    msg_payload = {
        "timestamp": unix_timestamp,
        "devices_detected": int(devices_detected)
    }

    json_msg_payload = json.dumps(msg_payload, separators=(",", ":"))

    result = client.publish(topic, json_msg_payload)

    # result: [0, 1]
    status = result[0]
    if status == 0:
        print(f"Send `{msg_payload}` to topic `{topic}`.")
        return True
    else:
        print("\nFailed to publish mqtt message.")
        # Save measurement in database
        store_pending_measurement(unix_timestamp, devices_detected)
        return False

# Insert pending measurement in database
def store_pending_measurement(unix_timestamp, devices_detected):
    conn = sqlite3.connect('/home/kali/Desktop/DB/StoredMeasurements.db' , timeout=30)
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO PendingMeasurements VALUES (?, ?) """, (unix_timestamp, devices_detected))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Measurement '({unix_timestamp},{devices_detected})' stored in the database.")


# Get first pending measurement from database
def get_1st_pending_measurement():
    conn = sqlite3.connect('/home/kali/Desktop/DB/StoredMeasurements.db' , timeout=30)
    cursor = conn.cursor()
    
    first_row = cursor.execute("""SELECT * FROM PendingMeasurements ORDER BY Timestamp ASC LIMIT 1 """).fetchone()

    conn.commit()
    cursor.close()
    conn.close()

    if first_row is None:
        # No pending measurements, database is empty
        print("There are no pending measurements, database is empty.")
        return None
    else:
        return first_row
        

# Remove first pending measurement from database
def remove_1st_pending_measurement():
    conn = sqlite3.connect('/home/kali/Desktop/DB/StoredMeasurements.db' , timeout=30)
    cursor = conn.cursor()
    
    cursor.execute("""DELETE FROM PendingMeasurements WHERE Timestamp IN (SELECT Timestamp FROM PendingMeasurements ORDER BY Timestamp ASC LIMIT 1)""")

    conn.commit()
    cursor.close()
    conn.close()


def check_config_mode():
    configuration_mode = ''
    while configuration_mode not in ("1","2"):

        configuration_mode = input("Please choose a configuration mode (1/2):").strip()

        if not (configuration_mode == "1" or configuration_mode == "2"):
            print("Please enter a configuration mode.")

    return configuration_mode

def confirm(question):
    confirmation = ''
    while confirmation not in ("Y", "y", "yes", "Yes", "YES", "n","N","No", "no", "NO"):

        confirmation = input(question).strip()

        if confirmation == "Yes" or confirmation == "Y" or confirmation == "yes" or confirmation == "y" or confirmation == "YES":
            break

        elif confirmation == "n" or confirmation == "N" or confirmation == "no" or confirmation == "No" or confirmation == "NO":
            print("Exit program.")
            print("------------------------------------------------------------------")
            exit(0)
        else:
            print("Please enter yes/no.")

def change_power_filtration(power_filtration):

    if not (int(power_filtration) >= -100 and int(power_filtration) <= 0):
        print("Value inserted in not correct. Packet filtration must be inside [-100, 0] dB. ('0' for no Packet Filtration).")
        exit(0)

    else:

        # Stop the current Wi-fi detection processes
        cmd = "sudo pkill airodump-ng"
        os.system(cmd)

        # Access the airodump-ng.c file
        f = open(AIRODUMP_FILEPATH, 'r')
        filecontent = f.readlines()

        # Change the power filtration value to the value passed in the argument
        if power_filtration == 0:
            # Comment line (no packet power filtration)
            filecontent[105] = f"//#define PACKET_POWER_FILTRATION {power_filtration}\n"
        else:
            # Add packet power filtration
            filecontent[105] = f"#define PACKET_POWER_FILTRATION {power_filtration}\n"


        # Re-write file with everything back
        with open(AIRODUMP_FILEPATH, 'w') as f:
            f.writelines(filecontent)


        with open(os.devnull, 'wb') as devnull:
            commands = "sudo make uninstall; make; sudo make install"
            subprocess.run(commands, cwd='/home/kali/Desktop/aircrack-ng-1.7/', shell=True, stdout=devnull, stderr=subprocess.STDOUT)

def compare_db_with_cronjobs():
    
    #Obter parametros da base de dados local

    connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
    cwifi = connwifi.cursor()

    sensor_configuration = cwifi.execute("""SELECT * FROM SensorConfiguration""").fetchall()

    
    if len(sensor_configuration) > 0:
        status_db = sensor_configuration[0][4]
        upload_periodicity_db = sensor_configuration[0][10]
        reboot_periodicity_db = sensor_configuration[0][13]
        reboot_time_db = sensor_configuration[0][14]

        sensor_communication = cwifi.execute("""SELECT * FROM SensorCommunication""").fetchall()
        
        detection_interface_db = sensor_communication[0][6]

        cwifi.close()
        connwifi.close()

        #Obter parametros dos cronjobs
        cmd = "crontab -u kali -l"
        output_lines = subprocess.check_output(cmd, shell=True).decode("utf-8").splitlines(keepends=False)


        first_chars_status = []

        for i in range(len(output_lines)):

            # status
            if i == 10 or i == 11 or i == 13:
                first_chars_status.append(output_lines[i][0])

            # detection interface
            if i == 10: 
                detection_interface_cron = output_lines[i].split(" ")[-1]

            # upload periodicity
            elif i == 13:
                upload_periodicity_cron = int(output_lines[i].split(" ")[0][2:])

            # reboot periodicity and reboot time
            elif i == 19:

                if output_lines[i][0] == "#":
                    reboot_periodicity_cron == "noreboot"
                else:
                    cron_day = str(output_lines[i].split(" ")[2])
                    cron_day_of_week = str(output_lines[i].split(" ")[4])

                    if cron_day == "*":
                        if cron_day_of_week == "*":
                            reboot_periodicity_cron = "daily"
                        elif cron_day_of_week == "0":
                            reboot_periodicity_cron = "weekly"
                    elif cron_day == "*/2":
                        reboot_periodicity_cron = "everytwodays"
                    elif cron_day == "*/3":
                        reboot_periodicity_cron = "everythreedays"
                    elif cron_day == "1":
                        reboot_periodicity_cron = "monthly"        
                        
                reboot_time_cron = int(output_lines[i].split(" ")[1])


        status_cron = "Disabled"
        for char in first_chars_status:
            if char != "#":
                status_cron="Active"
                break
        

        #Comparar todos os parâmetros
        if status_db != status_cron or \
        detection_interface_db != detection_interface_cron or \
        upload_periodicity_db != upload_periodicity_cron or \
        reboot_periodicity_db != reboot_periodicity_cron or \
        reboot_time_db != reboot_time_cron:
            #Se houver um parametro diferente, invocar funcao 'write_crontab_file' com parametros da base de dados
            print("Different parameters from db to cronjobs. Rewritting tasks configuration file with parameters from database.")
            write_crontab_file(status_db, detection_interface_db, upload_periodicity_db, reboot_periodicity_db, reboot_time_db)

    else:
        print("Sensor is not configured. Cronjobs will not be compared.")


#Communication handover mechanism

def check_wifi_available():
    response = os.system("ping -c 1 127.0.0.1")
    if response == 0:
        set_wifi_available(True)
        return True
    else:
        set_wifi_available(False)
        return False
    
def check_wifi_connection():        
    wifiConnected = False
    interfaces = ni.interfaces()

    for iface in interfaces:
        if iface != 'lo' and len(ni.ifaddresses(iface)) > 2:
            wifiConnected = True
            break

    if wifiConnected:
        set_wifi_connected(True)
        return True
    else:
        set_wifi_connected(False)
        return False
     
def check_lora_available():
    cmd = "sudo rak811 -v hard-reset"
    output = subprocess.check_output(cmd, shell=True)

    if "Hard reset complete" in str(output):
        set_lora_available(True)
        return True
    else:
        set_lora_available(False)
        return False

def check_lora_connection():
    #RAK811 Firmware V3
    #(It is possible to check LoRa connection by running the
    # 'sudo rak811v3 -v get-config lora:status' command)

    #RAK811 Firmware V2
    #(It is required to send a message, there is no 
    # command for checking Lora network connection)

    cmd = "sudo rak811 -v send %"
    output = subprocess.check_output(cmd, shell=True, timeout=300)

    if "Message sent" in str(output):
        set_lora_connected(True)
        return True
    else:
        set_lora_connected(False)
        return False
            
def reestablish_wifi_connection():
    #Get upload interface
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        upload_interface = cwifi.execute("""SELECT Upload_Interface FROM SensorCommunication""").fetchone()[0]

        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to read upload interface from database.", error)

    #Restart upload interface
    cmd = f"sudo ip link set dev {upload_interface} down"
    os.system(cmd)

    cmd = f"sudo ip link set dev {upload_interface} up"
    os.system(cmd)

    #Check network connection
    if check_wifi_connection() == True:
        set_wifi_connected(True)
        decide_upload_technology()
        return True
    else:
        return False
 
def reestablish_lora_connection():

    if heliumNodeSetup() == True:
        decide_upload_technology()
        return True
    else:
        return False
 
def set_wifi_available(wifiAvailable:bool):
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        sensor_comm = cwifi.execute("""SELECT * FROM SensorCommunication""").fetchone() 

        if sensor_comm is None:
            cwifi.execute("""INSERT INTO SensorCommunication (WifiAvailable, Last_Update) VALUES (?, CURRENT_TIMESTAMP)""", (wifiAvailable,))
        else:
            cwifi.execute("""UPDATE SensorCommunication SET WifiAvailable=?, Last_Update=CURRENT_TIMESTAMP""", (wifiAvailable,))

        connwifi.commit()
        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to update database.", error)

def set_wifi_connected(wifiAvailable:bool):
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        cwifi.execute("""UPDATE SensorCommunication SET WifiConnected=?, Last_Update=CURRENT_TIMESTAMP""", (wifiAvailable,))

        connwifi.commit()
        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to update database.", error)

def set_lora_available(loraAvailable:bool):
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        sensor_comm = cwifi.execute("""SELECT * FROM SensorCommunication""").fetchone()

        if sensor_comm is None:
            cwifi.execute("""INSERT INTO SensorCommunication (LoRaAvailable, Last_Update) VALUES (?, CURRENT_TIMESTAMP)""", (loraAvailable,))
        else:
            cwifi.execute("""UPDATE SensorCommunication SET LoRaAvailable=?, Last_Update=CURRENT_TIMESTAMP""", (loraAvailable,))

        connwifi.commit()
        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to update database.", error)

def set_lora_connected(loraAvailable:bool):
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        cwifi.execute("""UPDATE SensorCommunication SET LoRaConnected=?, Last_Update=CURRENT_TIMESTAMP""", (loraAvailable,))

        connwifi.commit()
        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to update database.", error)

def set_upload_technology(upload_technology):
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        cwifi.execute("""UPDATE SensorConfiguration SET Upload_Technology=?, Last_Update=CURRENT_TIMESTAMP""", (upload_technology,))

        connwifi.commit()
        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to update database.", error)

def get_upload_technology():

    print("Checking upload technology...")

    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        sensor_communication = cwifi.execute("""SELECT WifiAvailable, LoRaAvailable, WifiConnected, LoRaConnected FROM SensorCommunication""").fetchone()

        wifiAvailable = sensor_communication[0]
        loraAvailable = sensor_communication[1]
        wifiConnected = sensor_communication[2]
        loraConnected = sensor_communication[3]

        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to get data from database.", error)

    if wifiAvailable and wifiConnected:
        print("Upload via 'wifi' automatically selected for data communication.")
        return 'wifi'
    elif loraAvailable and loraConnected:
        print("Upload via 'lora' automatically selected for data communication.")
        return 'lora'

def decide_upload_technology():
    try:

        connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
        cwifi = connwifi.cursor()

        sensor_communication = cwifi.execute("""SELECT WifiAvailable, LoRaAvailable, WifiConnected, LoRaConnected FROM SensorCommunication""").fetchone()

        wifiAvailable = sensor_communication[0]
        loraAvailable = sensor_communication[1]
        wifiConnected = sensor_communication[2]
        loraConnected = sensor_communication[3]

        if wifiAvailable and wifiConnected:
            set_upload_technology('wifi')
        elif loraAvailable and loraConnected:
            set_upload_technology('lora')

        connwifi.commit()
        cwifi.close()
        connwifi.close()

    except sqlite3.Error as error:
        print("Failed to update database.", error)

def get_dev_eui():
    #Get dev_eui from LoRa board
    cmd = "sudo rak811 -v get-config dev_eui"
    dev_eui = subprocess.check_output(cmd, shell=True).decode('ascii')[:-1]

    return dev_eui

