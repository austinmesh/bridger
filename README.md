# ![bridger](./logo/logo-wide.png)

Bridger is a Meshtastic MQTT to InfluxDB metrics bridge. It listens to MQTT for protobuf messages and uses those to push metrics to InfluxDB.

## Usage

You will need InfluxDB and a MQTT broker running or available already.

Copy the the `.env.default` file to `.env` and view for the environment variables that can be set. The following are required:

 - MQTT_TOPIC
 - MQTT_BROKER
 - MQTT_USER
 - MQTT_PASS
 - INFLUXDB_V2_BUCKET
 - INFLUXDB_V2_ORG
 - INFLUXDB_V2_TOKEN
 - INFLUXDB_V2_URL

There are some other tunables as well:

 - INFLUXDB_V2_WRITE_PRECISION
 - MESHTASTIC_API_CACHE_TTL: The time to cache the Meshtastic API data. Defaults to 6 hours.
 - MESHTASTIC_KEY: The base64 encoded encryption key for the primary channel. Defaults to the the key provided by `AQ==`
 - MQTT_TEST_CHANNEL
 - MQTT_TEST_CHANNEL_ID
 - DISCORD_BOT_TOKEN
 - DISCORD_BOT_OWNER_ID
 - BRIDGER_ADMIN_ROLE
 - EMQX_API_KEY
 - EMQX_SECRET_KEY
 - EMQX_URL
 - LOG_PATH: Set this to a file path to log to a file. Defaults to `logs/bridger.log`


Then install the required packages in a Python virtual environment:

```bash
pip install -r requirements.txt
```

And run the script:

```bash
python -m bridger
```

## Node Setup

To get your Meshtastic node to send metrics to the MQTT broker you will need to set the following settings:

MQTT Module:

* Enabled: `Checked`
* MQTT Server Address: `mqtt.austinmesh.org`
* MQTT Username: <created_per_user>
* MQTT Password: <created_per_user>
* Encryption Enabled: `Unchecked`
* JSON Enabled: `Unchecked`
* TLS Enabled: `Unchecked`
* Root topic: `egr/home`

Primary Channel:

* Uplink Enabled: `Checked`
