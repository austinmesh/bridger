## Additional To Add

* TEXT_MESSAGE_APP
* ADMIN_APP
* ROUTING_APP

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

### Known schema tradeoffs

`long_name` and `short_name` are tags on the `node` measurement, so renaming a node forks its
series and the old one lives on until retention expires it. Accepted deliberately: the mesh is
small enough that the cardinality growth is slow, and demoting them to fields would split every
node series at the cutover and break any dashboard query that groups or filters by name.
Revisit if series count becomes a problem.

Deduplication is scoped by `(gateway_id, packet_id)`, so every gateway that hears a packet
writes its own point. That is what makes `rx_snr`/`rx_rssi` meaningful per gateway and what
makes `/bridger-mqtt is-alive` accurate, at the cost of multiplying point count by the average
gateway fan-out.

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

Updating the requirements lock files

Both locks are generated with `uv` and pinned to the container's Linux platform, so they
resolve identically no matter which machine regenerates them:

```bash
uv pip compile pyproject.toml --strip-extras \
  --python-platform x86_64-unknown-linux-gnu --python-version 3.12 -o requirements.txt

uv pip compile pyproject.toml --extra test --strip-extras \
  --python-platform x86_64-unknown-linux-gnu --python-version 3.12 -o requirements-dev.txt
```

`requirements.txt` is runtime only (what the container installs); `requirements-dev.txt` adds
the `test` extra and is what CI installs.

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
