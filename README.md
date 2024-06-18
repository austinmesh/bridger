# bridger

Bridger is a Meshtastic MQTT to InfluxDB metrics birdge. It listens to mQTT for protobuf messages and uses those to push metrics to InfluxDB.

## Usage

You will need InfluxDB and a MQTT broker running or available already.

Copy the the `.env.default` file to `.env` and view for the environment variables that can be set. The following are required:

 - MQTT_TOPIC
 - MQTT_BROKER
 - MQTT_USER
 - MQTT_PASS
 - INFLUX_BUCKET
 - INFLUX_ORG
 - INFLUX_TOKEN
 - INFLUX_URL

Then install the required packages in a Python virtual environment:

```bash
pip install -r requirements.txt
```

And run the script:

```bash
python -m bridge.mqtt
```
