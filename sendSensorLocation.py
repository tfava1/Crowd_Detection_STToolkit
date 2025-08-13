import sqlite3
import datetime as dt
import pytz
import matplotlib.pyplot as plt; plt.rcdefaults()
import os
import json

from sensorFunctions import *


# Read sensor configuration from database

try:
    connwifi= sqlite3.connect('/home/kali/Desktop/DB/SensorConfiguration.db' , timeout=30)
    cwifi = connwifi.cursor()

    sensor_configuration = cwifi.execute("""SELECT * FROM SensorConfiguration""").fetchall()

    #Sensor configuration
    if len(sensor_configuration) != 0:
        sensor_UUID = sensor_configuration[0][0]
        sensor_name = sensor_configuration[0][1]
        latitude = sensor_configuration[0][2]
        longitude = sensor_configuration[0][3]
        cloud_ip_addr = sensor_configuration[0][6]
        influx_org = sensor_configuration[0][7]
        influx_bucket = sensor_configuration[0][8]
        influx_token = sensor_configuration[0][9]
        uploadTechnology = sensor_configuration[0][12]

        if uploadTechnology.lower() == "wifi":
            ip_address = cwifi.execute("""SELECT IP_Address FROM SensorCommunication""").fetchone()[0]


    else:
        print("Failed to read sensor configuration from local database. Please make sure to \nconfigure a sensor configuration by running the 'sensorConfiguration.py' script first.")
        exit(0)

except sqlite3.Error as error:
    print("Failed to read sensor configuration from local database.")
    exit(0)


dataAtual=dt.datetime.now(pytz.utc).replace(tzinfo=None)


location = {
    "latitude": latitude,
    "longitude": longitude
}

json_location = json.dumps(location, separators=(",", ":"))

# Send sensor location to InfluxDB
if uploadTechnology.lower() == "wifi":
    publish_location_mqtt_message(json_location, f"sttoolkit-test/mqtt/wifi/sensorLocation/{influx_bucket}/{ip_address}/{sensor_name}/{sensor_UUID}")

    #cmd =f"curl -i   --request POST \"http://{cloud_ip_addr}:8086/api/v2/write?org={influx_org}&bucket={influx_bucket}&precision=s\"  \
     #                --header \"Authorization: Token {influx_token}\"  \
      #               --header \"Content-Type: text/plain; charset=utf-8\"  \
       #              --header \"Accept: application/json\" \
        #             --data-binary 'sensorLocation,sensor_UUID={sensor_UUID},sensor_name={sensor_name} latitude={latitude},longitude={longitude} {str(int( (dataAtual - dt.datetime(1970,1,1)).total_seconds()))}'"
    #os.system(cmd)

    print(f"Location '({latitude},{longitude})' was sent to the cloud server for sensor '{sensor_name}'.")

