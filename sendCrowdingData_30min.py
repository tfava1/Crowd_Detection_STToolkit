import sqlite3
import datetime as dt
import matplotlib.pyplot as plt; plt.rcdefaults()
import subprocess
import os
import pytz
import uuid
import netifaces as ni

from sensorFunctions import *

# Read sensor configuration from database

try:
    connwifi= sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db' , timeout=30)
    cwifi = connwifi.cursor()

    sensor_configuration = cwifi.execute("""SELECT * FROM SensorConfiguration""").fetchall()

    #Sensor configuration
    if len(sensor_configuration) != 0:
        sensorUUID = sensor_configuration[0][0]
        sensorName = sensor_configuration[0][1]
        influxdb_bucket = sensor_configuration[0][8]
        slidingWindow = sensor_configuration[0][11]
        uploadTechnology = sensor_configuration[0][12]

        if uploadTechnology.lower() == "wifi":
            ip_address = cwifi.execute("""SELECT IP_Address FROM SensorCommunication""").fetchone()[0]
            wifi_connected = cwifi.execute("""SELECT WifiConnected FROM SensorCommunication""").fetchone()[0]

    else:
        print("Sensor is not currently configured. It is required a cloud IP address to connect to the cloud server via MQTT.\nPlease run the 'sensorConfiguration.py' script to configure the sensor.")
        exit(0)

except sqlite3.Error as error:
    print("Failed to read sensor configuration from local database.")
    exit(0)


#dataAtual=dt.datetime.now(pytz.utc).replace(tzinfo=None)
dataAtual=dt.datetime.now(pytz.utc)
dataAnalizar= dataAtual - dt.timedelta(minutes=30)


# Get number of devices detected from database
try:

    conndev= sqlite3.connect('/home/kali/Desktop/DB/DeviceRecords.db' , timeout=30)
    cdev = conndev.cursor()

    # Device counting - Data packets
    rows_data_packets = cdev.execute("""SELECT COUNT(*) FROM Data_Packets WHERE ((First_Record >= ? and First_Record <= ?) or (Last_Time_Found > ? and Last_Time_Found <= ?))""", (dataAnalizar, dataAtual, dataAnalizar, dataAtual)).fetchall()

    # Device counting - Probe Requests
    rows_probe_requests = cdev.execute("""SELECT COUNT(*) FROM Probe_Requests WHERE ((First_Record >= ? and First_Record <= ?) or (Last_Time_Found > ? and Last_Time_Found <= ?))""", (dataAnalizar, dataAtual, dataAnalizar, dataAtual)).fetchall()

    # Device counting - All
    detected_devices = rows_data_packets[0][0] + rows_probe_requests[0][0]

    cdev.close()
    conndev.close()

except sqlite3.Error as error:
    print("Failed to read number of devices detected from local database.")



# Upload via Wi-Fi
if uploadTechnology.lower() == "wifi" and wifi_connected:

    dataAtual_unix = int(dataAtual.timestamp())

    mqtt_confirmation = publish_detections_mqtt_message(dataAtual_unix, detected_devices, f"sttoolkit/mqtt/wifi/numdetectionstable30min/{influxdb_bucket}/{ip_address}/{sensorName}/{sensorUUID}")

    if mqtt_confirmation is True:

        # Check if exists a pending measurement to send
        while get_1st_pending_measurement_30_min() is not None:

            # Send first pending measurement from database, and wait for its confirmation
            unix_ts = get_1st_pending_measurement_30_min()[0]
            devices_detected = get_1st_pending_measurement_30_min()[1]

            mqtt_pend_confirmation = publish_detections_mqtt_message(unix_ts, devices_detected, f"sttoolkit/mqtt/wifi/numdetectionstable30min/{influxdb_bucket}/{ip_address}/{sensorName}/{sensorUUID}")

            if mqtt_pend_confirmation is True:
                # Remove first pending measurement from database
                remove_1st_pending_measurement_30_min()
                continue
            else:
                break


# Upload via LoRa
elif uploadTechnology.lower() == "lora":

    # Send message to Helium
    cmd = f"sudo rak811 -v send \"{detected_devices},{influxdb_bucket},{sensorName}\""
    output = subprocess.check_output(cmd, shell=True, timeout=300)

    #If message was not sent
    if "RAK811 timeout" in str(output) or "error" in str(output):

        #Check LoRa connection
        if check_lora_connection() == False:

            print("There is no lora connection. Trying to reconnect to Helium network...")

            #If no LoRa connection, try to reestablish it
            reestablish_lora_connection()

    else:

        # Check if downlink message is available
        if "No downlink available" in str(output):
            print("Downlink not available.")
        else:
            print(f"Downlink message received: '{output}'.")

            #Payload parsing and decoding
            data_payload_split = str(output).split('Data: ', 1)[1]
            data_payload_hex = data_payload_split.split('\\n')[0]
            payload = bytes.fromhex(data_payload_hex).decode('utf-8')

            print(f"Received '{payload}'.")

            # Message received for rebooting sensor
            if payload == "r":
                print("Message received for rebooting sensor")
                cmd ="sudo reboot"
                os.system(cmd)

            # Message received for activating detection on sensor
            elif payload == "a":
                print("Message received for activating detection on sensor")
                receive_active()

            # Message received for disabling detection on sensor
            elif payload == "dis":
                print("Message received for disabling detection on sensor")
                receive_disable()

            else:

                    # Check type of message received rather than general actions ('c', 'd', or 'del')
                    type_msg = payload.split(",")[0]

                    # Message received for updating sensor configuration
                    if type_msg == 'c':
                        print("Message received for updating sensor configuration")

                        #Number of payload segments
                        segments_numb = int(payload.split(",")[1])

                        #If the payload was not segmented, interpret it right away
                        if segments_numb == 1:
                            update_config("lora", payload[6:])

                        #If the payload was segmented, reconstruct it
                        elif segments_numb > 1:

                            #Get current segment
                            curr_segment = int(payload.split(",")[2])

                            if curr_segment == 1: file = open("/home/kali/Desktop/payload_config.txt", 'w+')
                            else:                 file = open("/home/kali/Desktop/payload_config.txt", 'a+')

                            #Append payload
                            file.write(payload[6:])

                            if curr_segment == segments_numb:
                                file.seek(0)
                                rec_payload = file.readline().strip('\n')
                                update_config("lora", rec_payload)

                            file.close()

                        else:
                            print("Number of segments received from message is incorrect. Exiting program.")
                            exit(0)

                    # Message received for updating default configuration
                    elif type_msg == "d":
                        print("Message received for updating default configuration")

                        if payload.split(",")[1].isnumeric and len(payload.split(",")[1]) == 1:

                            #Number of payload segments
                            segments_numb = int(payload.split(",")[1])

                            #If the payload was not segmented, interpret it right away
                            if segments_numb == 1:
                                update_default(payload[6:])

                            #If the payload was segmented, reconstruct it
                            elif segments_numb > 1:

                                #Get current segment
                                curr_segment = int(payload.split(",")[2])

                                if curr_segment == 1: file = open("/home/kali/Desktop/payload_config.txt", 'w+')
                                else:                 file = open("/home/kali/Desktop/payload_config.txt", 'a+')

                                #Append payload
                                file.write(payload[6:])

                                if curr_segment == segments_numb:
                                    file.seek(0)
                                    rec_payload = file.readline().strip('\n')
                                    update_default(rec_payload)

                                file.close()

                    # Message received for deleting sensor configuration
                    elif type_msg == 'del':
                        print("Message received for deleting sensor configuration")

                        # Check if message is for this sensor from payload
                        sensor_uuid_payload = payload.split(",")[1]

                        try:
                            connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
                            cwifi = connwifi.cursor()

                            uuid_from_mac_addr = cwifi.execute("""SELECT Sensor_UUID from SensorConfiguration""").fetchone()

                            if uuid_from_mac_addr is None:
                                uuid_from_mac_addr = uuid.getnode()
                            else:
                                uuid_from_mac_addr = uuid_from_mac_addr[0]

                        except sqlite3.Error as error:
                            print("Error while connecting to database.", error)

                        if str(sensor_uuid_payload) == str(uuid_from_mac_addr):
                            delete_config()

                        else:
                            print("Number of segments received from message is incorrect. Exiting program.")
                            exit(0)

                    # Message received for specifically rebooting this sensor
                    elif type_msg == 'r':

                        # Check if message is for this sensor from payload
                        sensor_uuid_payload = payload.split(",")[1]

                        try:
                            connwifi = sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db', timeout=30)
                            cwifi = connwifi.cursor()

                            uuid_from_mac_addr = cwifi.execute("""SELECT Sensor_UUID from SensorConfiguration""").fetchone()

                            if uuid_from_mac_addr is None:
                                uuid_from_mac_addr = uuid.getnode()
                            else:
                                uuid_from_mac_addr = uuid_from_mac_addr[0]

                        except sqlite3.Error as error:
                            print("Error while connecting to database.", error)

                        if str(sensor_uuid_payload) == str(uuid_from_mac_addr):
                            os.sys("sudo reboot")

                        else:
                            print("Number of segments received from message is incorrect. Exiting program.")
                            exit(0)

else:
    print("WARNING: No communication available for sending crowding measurements! \n\
        Please check the network conectivity for uploading data to the cloud server.")

    dataAtual_unix = int(dataAtual.timestamp())

    print("\nFailed to publish mqtt message.")
    print("\nSaving detection in database to send later, when conection available.")
    #save measurement in database
    store_pending_measurement_30_min(dataAtual_unix, detected_devices)

cwifi.close()
connwifi.close()






