## Protobuf Messages

NodeInfo:

```protobuf
packet {
  from: 1253775432
  to: 2363982982
  decoded {
    portnum: NODEINFO_APP
    payload: "\n\t!4abb1848\022\017LetThereBeLight\032\004LTBL"\006\362mJ\273\030H(\t"
    want_response: true
  }
  id: 411096390
  rx_time: 1718344304
  rx_snr: -19.5
  hop_limit: 4
  rx_rssi: -94
  hop_start: 4
}
channel_id: "LongFast"
gateway_id: "!0c18aaf4"
```

BatteryInfo:

```protobuf
packet {
  from: 1439175448
  to: 4294967295
  decoded {
    portnum: TELEMETRY_APP
    payload: "\r\267\263qf\022\016\035\354Q\230?%\240\364!?(\242\230\003"
  }
  id: 766366037
  rx_time: 1718727607
  rx_snr: 6.5
  hop_limit: 6
  rx_rssi: -14
  hop_start: 7
}
channel_id: "LongFast"
gateway_id: "!0c18aaf4"
```

## InfluxDB

### Queries

Get nodes in multiple ways:

Example #1:

```
from(bucket: "meshtastic")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_measurement"] == "node")
  |> sort(columns: ["_time"], desc: true)
  |> keep(columns: ["_from", "short_name", "long_name"])
  |> distinct(column: "_from")
  |> group(columns: ["_from"])
  |> yield(name: "nodes")
```

Example #2:

```
from(bucket: "meshtastic")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_measurement"] == "node")
  |> group(columns: ["_measurement", "_field", "_from"])
  |> pivot(columnKey: ["_field"], rowKey: ["_time", "_from", "short_name", "long_name"], valueColumn: "_value")
  |> drop(columns: ["_start", "_stop"])
  |> last(column: "_time")
  |> yield(name: "nodes")
```


## Commands

Updating requirements.txt

```bash
pri -v $PWD:/bridger -w /bridger docker.io/library/python:3.12 bash -c "pip install pip-tools; pip-compile --strip-extras"
```
