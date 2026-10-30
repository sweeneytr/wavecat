#!/usr/bin/env python3
"""Create the Wavecat storage alerts in Grafana through its provisioning API.

Run where Grafana is reachable (the host can reach the pod IP):

    GRAFANA_URL=http://<pod-ip>:3000 GRAFANA_USER=admin GRAFANA_PASSWORD=... \
    NTFY_URL=https://ntfy.sh NTFY_TOPIC=... python3 apply.py [--dry-run]

It is idempotent: it overwrites the notification template, the "ntfy" contact point, the root notification
policy and the "storage" rule group. The ntfy topic is a secret (free ntfy.sh topics are public by name), so it is
only read from the environment and ends up in Grafana's database, never in git. docs/zfs-observability.md has the
rule table and the reasoning.
"""
import base64
import json
import os
import sys
import urllib.request

PROM_UID = "a35af9d3-363d-4b66-b426-d15344c2e1a8"
FOLDER = "wavecat"
GROUP = "storage"

def smart(expr):
    """Attach serial_number and device_model to a SMART series so alerts name the physical disk."""
    return "%s * on (disk) group_left (serial_number, device_model) smartmon_device_info" % expr


# (title, expr, comparator, threshold, for, severity, noDataState, lookback seconds, summary)
# Summaries must not render a double quote or newline: they are placed inside a JSON string for ntfy.
RULES = [
    ("SmartPendingSectors", smart("smartmon_current_pending_sector_raw_value"), "gt", 0, "5m", "critical", "Alerting", 600,
     'Disk {{ $labels.disk }} ({{ $labels.serial_number }}) has {{ printf "%.0f" $values.B.Value }} pending sectors: unreadable and not yet remapped. The drive is failing, check the pool and replace it'),
    ("SmartOfflineUncorrectable", smart("smartmon_offline_uncorrectable_raw_value"), "gt", 0, "5m", "critical", "OK", 600,
     'Disk {{ $labels.disk }} ({{ $labels.serial_number }}) has {{ printf "%.0f" $values.B.Value }} offline-uncorrectable sectors'),
    ("SmartReallocatedRising", smart("increase(smartmon_reallocated_sector_ct_raw_value[1d])"), "gt", 0, "0s", "warning", "OK", 90000,
     'Disk {{ $labels.disk }} ({{ $labels.serial_number }}) reallocated {{ printf "%.0f" $values.B.Value }} more sectors in the last day'),
    ("SmartHealthFailed", smart("smartmon_device_smart_healthy"), "lt", 1, "0s", "critical", "OK", 600,
     'SMART overall health FAILED on {{ $labels.disk }} ({{ $labels.serial_number }})'),
    ("ZfsPoolNotOnline", "zfs_pool_healthy", "lt", 1, "2m", "critical", "Alerting", 600,
     'ZFS pool {{ $labels.pool }} is not ONLINE (degraded or faulted)'),
    ("ZfsVdevOffline", "zfs_vdev_online", "lt", 1, "2m", "critical", "OK", 600,
     'ZFS vdev {{ $labels.vdev }} is not online'),
    ("ZfsErrorsSinceBoot", "zfs_vdev_read_errors + on (pool, vdev, type, parent, serial) zfs_vdev_write_errors "
     "+ on (pool, vdev, type, parent, serial) zfs_vdev_checksum_errors", "gt", 0, "0s", "warning", "OK", 600,
     'ZFS saw {{ printf "%.0f" $values.B.Value }} I/O or checksum errors on {{ $labels.vdev }} since boot'),
    ("ZfsDataErrors", "zfs_pool_data_errors", "gt", 0, "0s", "critical", "OK", 600,
     'ZFS pool {{ $labels.pool }} reports {{ printf "%.0f" $values.B.Value }} permanent data errors'),
    ("ZfsScrubOverdue",
     '(time() - max(zfs_pool_scan_last_end_timestamp_seconds{function="scrub"})) / 86400 '
     'and on() (max(zfs_pool_scan_in_progress{function="scrub"}) == 0)', "gt", 35, "1h", "warning", "OK", 600,
     'No ZFS scrub has finished for {{ printf "%.0f" $values.B.Value }} days. The monthly scrub did not run; start one with: zpool scrub wavecat'),
    ("ZfsLastScrubErrors", 'zfs_pool_scan_last_errors{function="scrub"}', "gt", 0, "0s", "warning", "OK", 600,
     'The last ZFS scrub found {{ printf "%.0f" $values.B.Value }} errors'),
    ("ZfsPoolFull", "100 * (1 - zfs_zpool_free_bytes / zfs_zpool_size_bytes)", "gt", 80, "30m", "warning", "OK", 600,
     'ZFS pool is {{ printf "%.0f" $values.B.Value }} percent full'),
    ("DiskTemperatureHigh", smart("smartmon_temperature_celsius_raw_value"), "gt", 55, "10m", "warning", "OK", 600,
     'Disk {{ $labels.disk }} ({{ $labels.serial_number }}) is at {{ printf "%.0f" $values.B.Value }} C'),
    ("ZfsSnapshotJobStale", "(time() - zfs_autosnap_last_success_timestamp_seconds) / 3600", "gt", 36, "10m", "warning", "Alerting", 600,
     'The daily ZFS snapshot set {{ $labels.set }} has not succeeded for {{ printf "%.0f" $values.B.Value }} hours. Check: journalctl -t zfs-snap-auto'),
    ("ZfsSnapshotJobFailed", "zfs_autosnap_last_run_failed", "gt", 0, "0s", "warning", "OK", 600,
     'The last ZFS snapshot run of set {{ $labels.set }} failed. Check: journalctl -t zfs-snap-auto'),
    ("StorageCollectorStale",
     'time() - node_textfile_mtime_seconds{file=~".*/(zfs_health|zfs_zpool).prom"}', "gt", 900, "5m", "warning", "Alerting", 600,
     'The host ZFS metrics file {{ $labels.file }} has not been updated for {{ printf "%.0f" $values.B.Value }} seconds'),
    ("SmartCollectorStale",
     'time() - node_textfile_mtime_seconds{file=~".*/smartmon.prom"}', "gt", 3600, "5m", "warning", "Alerting", 600,
     'The host SMART metrics file has not been updated for {{ printf "%.0f" $values.B.Value }} seconds'),
]


def rule_json(r):
    title, expr, cmp_, thr, for_, sev, nodata, lookback, summary = r
    return {
        "title": title, "ruleGroup": GROUP, "folderUID": FOLDER, "orgID": 1,
        "condition": "C", "noDataState": nodata, "execErrState": "Error", "for": for_,
        "annotations": {"summary": summary}, "labels": {"severity": sev, "area": "storage"}, "isPaused": False,
        "data": [
            {"refId": "A", "queryType": "", "relativeTimeRange": {"from": lookback, "to": 0}, "datasourceUid": PROM_UID,
             "model": {"refId": "A", "expr": expr, "instant": True, "range": False, "intervalMs": 1000, "maxDataPoints": 43200}},
            {"refId": "B", "queryType": "", "relativeTimeRange": {"from": lookback, "to": 0}, "datasourceUid": "__expr__",
             "model": {"refId": "B", "type": "reduce", "expression": "A", "reducer": "last",
                       "settings": {"mode": "dropNN"}, "datasource": {"type": "__expr__", "uid": "__expr__"}}},
            {"refId": "C", "queryType": "", "relativeTimeRange": {"from": lookback, "to": 0}, "datasourceUid": "__expr__",
             "model": {"refId": "C", "type": "threshold", "expression": "B",
                       "conditions": [{"evaluator": {"type": cmp_, "params": [thr]}}],
                       "datasource": {"type": "__expr__", "uid": "__expr__"}}},
        ],
    }


def template(topic):
    return ('{{ define "ntfy.json" -}}\n'
            '{"topic":"%s",'
            '"title":"{{ if eq .Status "firing" }}ALERT{{ else }}RESOLVED{{ end }}: {{ .CommonLabels.alertname }}",'
            '"message":"{{ range .Alerts }}{{ .Annotations.summary }}. {{ end }}",'
            '"priority":{{ if eq .Status "resolved" }}3{{ else if eq .CommonLabels.severity "critical" }}5{{ else }}4{{ end }},'
            '"tags":["{{ if eq .Status "firing" }}warning{{ else }}white_check_mark{{ end }}","grafana"]}\n'
            '{{- end }}\n') % topic


def main():
    dry = "--dry-run" in sys.argv
    base = os.environ["GRAFANA_URL"].rstrip("/")
    auth = base64.b64encode(("%s:%s" % (os.environ["GRAFANA_USER"], os.environ["GRAFANA_PASSWORD"])).encode()).decode()
    topic, ntfy_url = os.environ["NTFY_TOPIC"], os.environ.get("NTFY_URL", "https://ntfy.sh")

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Basic " + auth, "Content-Type": "application/json",
                                              "X-Disable-Provenance": "true"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode()
                return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    plan = [
        ("PUT", "/api/v1/provisioning/templates/ntfy", {"template": template(topic), "version": ""}),
        ("GET", "/api/v1/provisioning/contact-points", None),
    ]
    if dry:
        print(json.dumps([rule_json(r) for r in RULES][0], indent=1)[:900])
        print("%d rules; template preview:\n%s" % (len(RULES), template("TOPIC")))
        return 0

    print("template:", call("PUT", "/api/v1/provisioning/templates/ntfy", {"template": template(topic), "version": ""})[0])
    cp = {"name": "ntfy", "type": "webhook", "disableResolveMessage": False,
          "settings": {"url": ntfy_url, "httpMethod": "POST", "payload": {"template": '{{ template "ntfy.json" . }}'}}}
    code, existing = call("GET", "/api/v1/provisioning/contact-points")
    uid = next((c["uid"] for c in existing if c["name"] == "ntfy"), None) if isinstance(existing, list) else None
    if uid:
        cp["uid"] = uid
        print("contact point (update):", call("PUT", "/api/v1/provisioning/contact-points/" + uid, cp)[0])
    else:
        print("contact point (create):", call("POST", "/api/v1/provisioning/contact-points", cp)[0])
    policy = {"receiver": "ntfy", "group_by": ["alertname", "disk"], "group_wait": "30s", "group_interval": "5m",
              "repeat_interval": "12h"}
    print("policy:", call("PUT", "/api/v1/provisioning/policies", policy)[0])
    group = {"title": GROUP, "folderUid": FOLDER, "interval": 60, "rules": [rule_json(r) for r in RULES]}
    code, resp = call("PUT", "/api/v1/provisioning/folder/%s/rule-groups/%s" % (FOLDER, GROUP), group)
    print("rule group:", code, "" if code < 300 else str(resp)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
