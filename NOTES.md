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

NeighborInfo:

```protobuf
packet {
  from: 1787528378
  to: 4294967295
  decoded {
    portnum: NEIGHBORINFO_APP
    payload:
      node_id: 1787528378
      last_sent_by_id: 1787528378
      node_broadcast_interval_secs: 900
      neighbors {
        node_id: 2363982982
        snr: 6
      }
      neighbors {
        node_id: 3180124126
        snr: -11
      }
      neighbors {
        node_id: 1921163711
        snr: -16
      }
      neighbors {
        node_id: 1431471144
        snr: -15.75
      }
  }
  id: 1279148956
  rx_time: 1720024942
  hop_limit: 4
  hop_start: 4
}
channel_id: "LongFast"
gateway_id: "!6a8b84ba"
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

## Grafana

Node graph example JSON:

```json
{
  "datasource": {
    "uid": "ddrd8s18boflse",
    "type": "influxdb"
  },
  "gridPos": {
    "h": 8,
    "w": 12,
    "x": 0,
    "y": 0
  },
  "id": 1,
  "options": {
    "nodes": {
      "mainStatUnit": "dB"
    },
    "edges": {
      "mainStatUnit": "Node"
    }
  },
  "pluginVersion": "11.0.1",
  "targets": [
    {
      "datasource": {
        "type": "influxdb",
        "uid": "ddrd8s18boflse"
      },
      "query": "from(bucket: \"meshtastic\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"neighbor\")\n  |> filter(fn: (r) => r[\"_field\"] == \"snr\")\n  |> group(columns: [\"_measurement\", \"_field\", \"neighbor_id\", \"node_id\"])\n  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)\n  |> rename(columns: {node_id: \"source\", neighbor_id: \"target\", _value: \"mainstat\"})\n  |> map(fn: (r) => ({r with \"id\": r.source + \"_\" + r.target, \"nodeRadius\": 10}))\n  |> keep(columns: [\"id\", \"source\", \"target\", \"mainstat\", \"nodeRadius\"])\n  |> group()\n  |> yield(name: \"edges\")",
      "refId": "edges"
    },
    {
      "datasource": {
        "uid": "ddrd8s18boflse",
        "type": "influxdb"
      },
      "refId": "nodes",
      "hide": false,
      "query": "sources = from(bucket: \"meshtastic\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"neighbor\")\n  |> filter(fn: (r) => r[\"_field\"] == \"node_broadcast_interval_secs\")\n  |> group(columns: [\"node_id\"])\n  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)\n  |> rename(columns: {node_id: \"id\"})\n  |> map(fn: (r) => ({r with \"title\": r.id, \"nodeRadius\": 10}))\n  |> keep(columns: [\"id\", \"title\", \"nodeRadius\"])\n  |> group()\n\ntargets = from(bucket: \"meshtastic\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"neighbor\")\n  |> filter(fn: (r) => r[\"_field\"] == \"node_broadcast_interval_secs\")\n  |> group(columns: [\"neighbor_id\"])\n  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)\n  |> rename(columns: {neighbor_id: \"id\"})\n  |> map(fn: (r) => ({r with \"title\": r.id, \"nodeRadius\": 10}))\n  |> keep(columns: [\"id\", \"title\", \"nodeRadius\"])\n  |> group()\n\nunion(tables: [sources, targets])"
    }
  ],
  "title": "New Panel",
  "type": "nodeGraph"
}
```
