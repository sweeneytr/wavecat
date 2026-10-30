#!/usr/bin/env python3
"""Generate the Wavecat Grafana dashboards as JSON files next to this script.

    python3 build.py            # (re)write the *.json files

The JSON files are what gets imported into Grafana (Dashboards > New > Import, or the API).
This script only generates them, so panels stay consistent.
Datasource UIDs are the ones provisioned in the live Grafana (Prometheus = Mimir, Loki).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROM = {"type": "prometheus", "uid": "a35af9d3-363d-4b66-b426-d15344c2e1a8"}
LOKI = {"type": "loki", "uid": "fcaeeb5a-765a-47a7-9ecb-61c844f29aad"}
FOLDER = {"uid": "wavecat", "title": "Wavecat"}


class Dash:
    def __init__(self, uid, title, description, variables=None, refresh="1m", span="now-6h"):
        self.uid, self.title, self.description = uid, title, description
        self.panels, self._id, self.y = [], 0, 0
        self.templating = variables or []
        self.refresh, self.span = refresh, span

    def _next(self):
        self._id += 1
        return self._id

    def row(self, title):
        self.panels.append({"id": self._next(), "type": "row", "title": title, "collapsed": False,
                            "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []})
        self.y += 1

    def _panel(self, kind, title, targets, x, w, h, ds, desc="", fc=None, options=None):
        p = {"id": self._next(), "type": kind, "title": title, "description": desc, "datasource": ds,
             "gridPos": {"h": h, "w": w, "x": x, "y": self.y}, "targets": targets,
             "fieldConfig": {"defaults": {}, "overrides": []}, "options": options or {}}
        if fc:
            p["fieldConfig"]["defaults"].update(fc)
        return p

    def place(self, panels, h):
        """panels: list of (builder-result, width). Lays them out left to right on one row."""
        x = 0
        for p, w in panels:
            p["gridPos"].update({"x": x, "w": w, "h": h, "y": self.y})
            self.panels.append(p)
            x += w
        self.y += h

    @staticmethod
    def _t(expr, legend="", ds=PROM, instant=False, fmt=None, ref="A"):
        t = {"refId": ref, "expr": expr, "legendFormat": legend, "datasource": ds}
        if instant:
            t["instant"] = True
            t["range"] = False
        if fmt:
            t["format"] = fmt
        return t

    def stat(self, title, expr, unit="short", desc="", thresholds=None, colorize="value", mappings=None, ds=PROM):
        steps = thresholds or [{"color": "green", "value": None}]
        fc = {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}, "mappings": mappings or [],
              "color": {"mode": "thresholds"}}
        opts = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": colorize, "graphMode": "area", "textMode": "auto", "justifyMode": "auto"}
        return self._panel("stat", title, [self._t(expr, instant=False, ds=ds)], 0, 4, 4, ds, desc, fc, opts)

    def ts(self, title, queries, unit="short", desc="", stack=False, fill=10, minv=None, maxv=None, ds=PROM):
        """queries: list of (expr, legend)."""
        targets = [self._t(e, l, ds=ds, ref=chr(65 + i)) for i, (e, l) in enumerate(queries)]
        custom = {"drawStyle": "line", "lineWidth": 1, "fillOpacity": fill, "showPoints": "never",
                  "spanNulls": True, "stacking": {"mode": "normal" if stack else "none", "group": "A"}}
        fc = {"unit": unit, "custom": custom}
        if minv is not None:
            fc["min"] = minv
        if maxv is not None:
            fc["max"] = maxv
        opts = {"legend": {"displayMode": "table" if len(queries) > 1 else "list", "placement": "bottom",
                           "calcs": ["lastNotNull", "max"] if len(queries) > 1 else []},
                "tooltip": {"mode": "multi", "sort": "desc"}}
        return self._panel("timeseries", title, targets, 0, 12, 8, ds, desc, fc, opts)

    def table(self, title, expr, desc="", unit="short", rename=None, hide=None, sort_by=None, ds=PROM):
        t = self._t(expr, instant=True, fmt="table", ds=ds)
        fc = {"unit": unit, "custom": {"align": "auto", "cellOptions": {"type": "auto"}}}
        p = self._panel("table", title, [t], 0, 12, 8, ds, desc, fc,
                        {"showHeader": True, "sortBy": [{"displayName": sort_by, "desc": True}] if sort_by else []})
        tr = [{"id": "organize", "options": {"excludeByName": {c: True for c in (hide or [])} | {"Time": True},
                                           "renameByName": rename or {}}}]
        p["transformations"] = tr
        return p

    def bargauge(self, title, expr, legend, unit="short", desc="", thresholds=None, ds=PROM, maxv=None):
        steps = thresholds or [{"color": "green", "value": None}]
        fc = {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}, "color": {"mode": "thresholds"}}
        if maxv is not None:
            fc["max"] = maxv
        t = self._t(expr, legend, instant=True, ds=ds)
        return self._panel("bargauge", title, [t], 0, 12, 8, ds, desc, fc,
                           {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})

    def logs(self, title, expr, desc=""):
        t = {"refId": "A", "expr": expr, "queryType": "range", "datasource": LOKI, "maxLines": 200}
        return self._panel("logs", title, [t], 0, 24, 10, LOKI, desc, None,
                           {"showTime": True, "wrapLogMessage": True, "enableLogDetails": True,
                            "sortOrder": "Descending", "dedupStrategy": "none", "prettifyLogMessage": False})

    def json(self):
        return {"uid": self.uid, "title": self.title, "description": self.description,
                "tags": ["wavecat"], "timezone": "browser", "schemaVersion": 39, "version": 1,
                "editable": True, "graphTooltip": 1, "refresh": self.refresh,
                "time": {"from": self.span, "to": "now"}, "panels": self.panels,
                "templating": {"list": self.templating}, "annotations": {"list": []}}


def var_query(name, label, query, include_all=True, multi=True, regex=""):
    return {"name": name, "label": label, "type": "query", "datasource": PROM,
            "query": {"query": query, "refId": f"var-{name}", "qryType": 1},
            "definition": query, "refresh": 2, "sort": 1, "includeAll": include_all,
            "multi": multi, "allValue": ".+", "regex": regex,
            "current": {"selected": True, "text": "All", "value": "$__all"} if include_all else {}}


def var_text(name, label):
    return {"name": name, "label": label, "type": "textbox", "query": "", "current": {"text": "", "value": ""}}


G, Y, R = {"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 1}


def cluster_overview():
    d = Dash("wc-cluster", "Cluster overview",
             "Health of the k3s node and everything scheduled on it (kube-state-metrics, cert-manager, Loki).")
    d.row("At a glance")
    d.place([
        (d.stat("Node ready", 'sum(kube_node_status_condition{condition="Ready",status="true"})', desc="Nodes reporting Ready",
                thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]), 3),
        (d.stat("Pods running", 'sum(kube_pod_status_phase{phase="Running"})'), 3),
        (d.stat("Not running", 'sum(kube_pod_status_phase{phase=~"Pending|Failed|Unknown"})',
                thresholds=[G, {"color": "orange", "value": 1}, {"color": "red", "value": 5}],
                desc="Pending, Failed or Unknown. A couple of known-broken apps keep this above zero."), 3),
        (d.stat("Below desired",
                'count(kube_deployment_spec_replicas - kube_deployment_status_replicas_available > 0) or vector(0)',
                thresholds=[G, {"color": "orange", "value": 1}]), 3),
        (d.stat("Restarts (1h)", 'round(sum(increase(kube_pod_container_status_restarts_total[1h])))',
                thresholds=[G, {"color": "orange", "value": 5}, {"color": "red", "value": 20}]), 3),
        (d.stat("Certificates ready", 'sum(certmanager_certificate_ready_status{condition="True"})'), 3),
        (d.stat("Certs < 21d",
                'count((certmanager_certificate_expiration_timestamp_seconds - time()) < 21*86400) or vector(0)',
                thresholds=[G, {"color": "orange", "value": 1}, {"color": "red", "value": 3}]), 3),
        (d.stat("PVCs", 'count(kube_persistentvolumeclaim_info)'), 3),
    ], 4)

    d.row("Pods and workloads")
    d.place([
        (d.ts("Pods by phase", [('sum by (phase) (kube_pod_status_phase == 1)', "{{phase}}")], stack=True, fill=40), 12),
        (d.ts("Container restarts by namespace (rate / 5m)",
              [('sum by (k8s_namespace) (increase(kube_pod_container_status_restarts_total[5m]))', "{{k8s_namespace}}")],
              stack=True, fill=40), 12),
    ], 8)
    d.place([
        (d.table("Pods restarting (last 6h)",
                 'sort_desc(sum by (k8s_namespace, k8s_pod_name, k8s_container_name) '
                 '(round(increase(kube_pod_container_status_restarts_total[6h]))) > 0)',
                 rename={"k8s_namespace": "Namespace", "k8s_pod_name": "Pod", "k8s_container_name": "Container", "Value": "Restarts"},
                 hide=["Time"], sort_by="Restarts"), 12),
        (d.table("Deployments / StatefulSets below desired replicas",
                 '(kube_deployment_spec_replicas - kube_deployment_status_replicas_available > 0) '
                 'or (kube_statefulset_replicas - kube_statefulset_status_replicas_ready > 0)',
                 rename={"k8s_namespace": "Namespace", "k8s_deployment_name": "Deployment", "statefulset": "StatefulSet", "Value": "Missing"},
                 hide=["instance", "job"]), 12),
    ], 8)

    d.row("Capacity (requests vs allocatable)")
    d.place([
        (d.ts("CPU requested vs allocatable (cores)",
              [('sum(kube_pod_container_resource_requests{resource="cpu"})', "requested"),
               ('sum(kube_node_status_allocatable{resource="cpu"})', "allocatable")], desc="Requests, not usage."), 12),
        (d.ts("Memory requested vs allocatable",
              [('sum(kube_pod_container_resource_requests{resource="memory"})', "requested"),
               ('sum(kube_node_status_allocatable{resource="memory"})', "allocatable")], unit="bytes"), 12),
    ], 8)
    d.place([
        (d.bargauge("Pods per namespace", 'sort_desc(count by (k8s_namespace) (kube_pod_info))', "{{k8s_namespace}}"), 12),
        (d.table("Persistent volumes",
                 'kube_persistentvolume_capacity_bytes * on (persistentvolume) group_left(k8s_namespace, persistentvolumeclaim) '
                 'max by (persistentvolume, k8s_namespace, persistentvolumeclaim) '
                 '(label_replace(kube_persistentvolumeclaim_info, "persistentvolume", "$1", "volumename", "(.+)"))',
                 unit="bytes", rename={"k8s_namespace": "Namespace", "persistentvolumeclaim": "Claim", "Value": "Capacity"},
                 hide=["instance", "job", "persistentvolume"], sort_by="Capacity"), 12),
    ], 8)

    d.row("Logs")
    d.place([(d.logs("Errors across the cluster",
                     '{k8s_namespace=~".+"} |~ "(?i)(error|fatal|panic|exception)" !~ "(?i)level=(info|debug)"',
                     desc="Pod logs matching error / fatal / panic / exception."), 24)], 10)
    return d


def apps():
    ns = var_query("namespace", "Namespace", 'label_values(kube_pod_info, k8s_namespace)')
    search = var_text("search", "Log filter")
    d = Dash("wc-apps", "Apps (k3s workloads)",
             "Per-namespace view of workloads: replicas, restarts, why containers stopped, logs and events.",
             variables=[ns, search])
    sel = 'k8s_namespace=~"$namespace"'
    d.row("Workloads")
    d.place([
        (d.stat("Pods", f'count(kube_pod_info{{{sel}}})'), 4),
        (d.stat("Running", f'sum(kube_pod_status_phase{{{sel},phase="Running"}})'), 4),
        (d.stat("Not running", f'sum(kube_pod_status_phase{{{sel},phase=~"Pending|Failed|Unknown"}})',
                thresholds=[G, {"color": "orange", "value": 1}]), 4),
        (d.stat("Restarts (1h)", f'round(sum(increase(kube_pod_container_status_restarts_total{{{sel}}}[1h])))',
                thresholds=[G, {"color": "orange", "value": 3}, {"color": "red", "value": 10}]), 4),
        (d.stat("Ready containers", f'sum(kube_pod_container_status_ready{{{sel}}})'), 4),
        (d.stat("Not ready", f'count(kube_pod_container_status_ready{{{sel}}} == 0) or vector(0)',
                thresholds=[G, {"color": "orange", "value": 1}]), 4),
    ], 4)
    d.place([
        (d.ts("Deployment replicas available vs desired",
              [(f'sum by (k8s_deployment_name) (kube_deployment_status_replicas_available{{{sel}}})', "{{k8s_deployment_name}} available"),
               (f'sum by (k8s_deployment_name) (kube_deployment_spec_replicas{{{sel}}})', "{{k8s_deployment_name}} desired")]), 12),
        (d.ts("Container restarts",
              [(f'sum by (k8s_pod_name, k8s_container_name) (increase(kube_pod_container_status_restarts_total{{{sel}}}[5m]))',
                "{{k8s_pod_name}} / {{k8s_container_name}}")], stack=True, fill=30), 12),
    ], 8)
    d.place([
        (d.table("Pods",
                 f'kube_pod_info{{{sel}}} * on (k8s_pod_uid) group_left(phase) (kube_pod_status_phase{{{sel}}} == 1)',
                 rename={"k8s_namespace": "Namespace", "k8s_pod_name": "Pod", "k8s_node_name": "Node", "phase": "Phase",
                         "created_by_kind": "Owner kind", "created_by_name": "Owner", "k8s_pod_ip": "Pod IP"},
                 hide=["Value", "instance", "job", "k8s_pod_uid", "host_ip", "host_network", "Value #A", "Value #B"]), 14),
        (d.table("Why containers last stopped",
                 f'kube_pod_container_status_last_terminated_reason{{{sel}}} == 1',
                 rename={"k8s_namespace": "Namespace", "k8s_pod_name": "Pod", "k8s_container_name": "Container", "reason": "Reason"},
                 hide=["Value", "instance", "job", "k8s_pod_uid"]), 10),
    ], 9)
    d.row("Resources requested")
    d.place([
        (d.ts("CPU requests by pod (cores)",
              [(f'sum by (k8s_pod_name) (kube_pod_container_resource_requests{{{sel},resource="cpu"}})', "{{k8s_pod_name}}")],
              stack=True, fill=30), 12),
        (d.ts("Memory requests by pod",
              [(f'sum by (k8s_pod_name) (kube_pod_container_resource_requests{{{sel},resource="memory"}})', "{{k8s_pod_name}}")],
              unit="bytes", stack=True, fill=30), 12),
    ], 8)
    d.row("Logs and events")
    d.place([(d.logs("Pod logs", '{k8s_namespace=~"$namespace"} |~ "(?i)$search"',
                     desc="Pod logs for the selected namespace(s). Type in 'Log filter' to narrow (regex, case-insensitive)."), 24)], 11)
    d.place([(d.logs("Kubernetes events", '{job=~".*kubernetes_events.*"} |~ "$namespace"',
                     desc="Cluster events collected by Alloy."), 24)], 8)
    return d


def ingress():
    d = Dash("wc-ingress", "Ingress (Traefik)",
             "Traffic through Traefik: request rates, errors, latency and connections. Service names carry the provider suffix.")
    d.row("Traffic")
    d.place([
        (d.stat("Requests / s", 'sum(rate(traefik_entrypoint_requests_total[5m]))', unit="reqps"), 4),
        (d.stat("5xx / s", 'sum(rate(traefik_entrypoint_requests_total{code=~"5.."}[5m])) or vector(0)', unit="reqps",
                thresholds=[G, {"color": "orange", "value": 0.05}, {"color": "red", "value": 1}]), 4),
        (d.stat("Error ratio (5xx)", 'sum(rate(traefik_entrypoint_requests_total{code=~"5.."}[5m])) / sum(rate(traefik_entrypoint_requests_total[5m]))',
                unit="percentunit", thresholds=[G, {"color": "orange", "value": 0.01}, {"color": "red", "value": 0.05}]), 4),
        (d.stat("Open connections", 'sum(traefik_open_connections)'), 4),
        (d.stat("Reload failures", 'sum(increase(traefik_config_reloads_failure_total[1h])) or vector(0)',
                thresholds=[G, {"color": "red", "value": 1}]), 4),
        (d.stat("TLS share", 'sum(rate(traefik_entrypoint_requests_tls_total[5m])) / sum(rate(traefik_entrypoint_requests_total[5m]))',
                unit="percentunit"), 4),
    ], 4)
    d.place([
        (d.ts("Requests / s by response class",
              [('sum by (class) (label_replace(rate(traefik_entrypoint_requests_total{code=~"[1-5].."}[5m]), "class", "${1}xx", "code", "(\\\\d)\\\\d\\\\d"))', "{{class}}")],
              unit="reqps", stack=True, fill=40), 12),
        (d.ts("Request latency (entrypoint)",
              [('histogram_quantile(0.5, sum by (le) (rate(traefik_entrypoint_request_duration_seconds_bucket[5m])))', "p50"),
               ('histogram_quantile(0.95, sum by (le) (rate(traefik_entrypoint_request_duration_seconds_bucket[5m])))', "p95"),
               ('histogram_quantile(0.99, sum by (le) (rate(traefik_entrypoint_request_duration_seconds_bucket[5m])))', "p99")],
              unit="s"), 12),
    ], 8)
    d.row("By backend service")
    d.place([
        (d.bargauge("Requests / s by service (top 12)",
                    'topk(12, sum by (service) (rate(traefik_service_requests_total[5m])))', "{{service}}", unit="reqps"), 12),
        (d.bargauge("5xx / s by service",
                    'topk(12, sum by (service) (rate(traefik_service_requests_total{code=~"5.."}[5m]))) > 0', "{{service}}", unit="reqps",
                    thresholds=[G, {"color": "orange", "value": 0.05}, {"color": "red", "value": 1}]), 12),
    ], 8)
    d.place([
        (d.ts("Open connections",
              [('sum by (entrypoint) (traefik_entrypoint_open_connections)', "{{entrypoint}}")], stack=True, fill=30), 12),
        (d.ts("Traffic (bytes / s)",
              [('sum(rate(traefik_entrypoint_requests_bytes_total[5m]))', "request bytes"),
               ('sum(rate(traefik_entrypoint_responses_bytes_total[5m]))', "response bytes")], unit="Bps"), 12),
    ], 8)
    d.row("Logs")
    d.place([(d.logs("Traefik logs", '{k8s_app_name="traefik"}'), 24)], 9)
    return d


def platform():
    d = Dash("wc-platform", "Platform services",
             "cert-manager, Argo CD, CoreDNS, sealed-secrets and the observability stack itself.")
    d.row("Certificates (cert-manager)")
    d.place([
        (d.stat("Ready", 'sum(certmanager_certificate_ready_status{condition="True"})'), 4),
        (d.stat("Not ready", 'sum(certmanager_certificate_ready_status{condition!="True"} == 1) or vector(0)',
                thresholds=[G, {"color": "red", "value": 1}]), 4),
        (d.stat("ClusterIssuer ready", 'min(certmanager_clusterissuer_ready_status{condition="True"})',
                thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]), 4),
        (d.stat("Soonest expiry (days)", 'min(certmanager_certificate_expiration_timestamp_seconds - time()) / 86400', unit="d",
                thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 14}, {"color": "green", "value": 30}]), 4),
        (d.stat("ACME requests / s", 'sum(rate(certmanager_http_acme_client_request_count[15m]))', unit="reqps"), 4),
        (d.stat("Sync errors (1h)", 'sum(increase(certmanager_controller_sync_error_count[1h])) or vector(0)',
                thresholds=[G, {"color": "orange", "value": 1}]), 4),
    ], 4)
    d.place([
        (d.bargauge("Days until expiry (soonest 15)",
                    'bottomk(15, (certmanager_certificate_expiration_timestamp_seconds - time()) / 86400)', "{{namespace}}/{{name}}", unit="d",
                    thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 14}, {"color": "green", "value": 30}], maxv=90), 12),
        (d.ts("Controller sync calls vs errors",
              [('sum(rate(certmanager_controller_sync_call_count[5m]))', "sync calls"),
               ('sum(rate(certmanager_controller_sync_error_count[5m]))', "sync errors")], unit="ops"), 12),
    ], 8)

    d.row("Argo CD")
    d.place([
        (d.stat("Applications", 'count(argocd_app_info)'), 4),
        (d.stat("Synced", 'count(argocd_app_info{sync_status="Synced"})'), 4),
        (d.stat("Out of sync", 'count(argocd_app_info{sync_status!="Synced"}) or vector(0)',
                thresholds=[G, {"color": "orange", "value": 1}]), 4),
        (d.stat("Healthy", 'count(argocd_app_info{health_status="Healthy"})'), 4),
        (d.stat("Not healthy", 'count(argocd_app_info{health_status!="Healthy"}) or vector(0)',
                thresholds=[G, {"color": "orange", "value": 1}]), 4),
        (d.stat("Reconcile errors (1h)", 'sum(increase(argocd_app_reconcile_count{}[1h])) or vector(0)'), 4),
    ], 4)
    d.place([
        (d.table("Applications not Synced / Healthy",
                 'argocd_app_info{sync_status!="Synced"} or argocd_app_info{health_status!="Healthy"}',
                 rename={"name": "Application", "project": "Project", "sync_status": "Sync", "health_status": "Health"},
                 hide=["Value", "instance", "job", "namespace", "dest_namespace", "dest_server", "repo", "autosync_enabled",
                       "argocd_component", "operation", "k8s_namespace", "k8s_pod_name"]), 12),
        (d.ts("Application sync operations (rate / 15m)",
              [('sum by (phase) (rate(argocd_app_sync_total[15m]))', "{{phase}}")], unit="ops", stack=True, fill=40), 12),
    ], 8)

    d.row("DNS (CoreDNS)")
    d.place([
        (d.ts("Queries / s by type", [('sum by (type) (rate(coredns_dns_requests_total[5m]))', "{{type}}")], unit="reqps", stack=True, fill=30), 8),
        (d.ts("Responses / s by rcode", [('sum by (rcode) (rate(coredns_dns_responses_total[5m]))', "{{rcode}}")], unit="reqps", stack=True, fill=30), 8),
        (d.ts("Latency",
              [('histogram_quantile(0.95, sum by (le) (rate(coredns_dns_request_duration_seconds_bucket[5m])))', "p95"),
               ('histogram_quantile(0.99, sum by (le) (rate(coredns_dns_request_duration_seconds_bucket[5m])))', "p99")], unit="s"), 8),
    ], 8)

    d.row("Identity and secrets")
    d.place([
        (d.ts("Sealed-secrets unseal requests",
              [('sum by (status) (rate(sealed_secrets_controller_unseal_requests_total[15m]))', "{{status}}")], unit="ops"), 24),
    ], 8)

    d.row("Observability stack")
    d.place([
        (d.ts("Alloy running components",
              [('sum(alloy_component_controller_running_components)', "running"),
               ('sum(alloy_component_controller_evaluating)', "evaluating")]), 8),
        (d.ts("Loki dropped lines (Alloy processing)",
              [('sum by (reason) (rate(loki_process_dropped_lines_total[5m]))', "{{reason}}")], unit="ops", stack=True, fill=30), 8),
        (d.ts("Controller workqueue depth",
              [('sum by (name) (workqueue_depth)', "{{name}}")], stack=True, fill=30), 8),
    ], 8)
    d.place([(d.logs("Platform error logs",
                     '{k8s_namespace=~"argocd|cert-manager|monitoring|infra|kube-system|secret-generator|metallb-system|tailscale"} '
                     '|~ "(?i)(error|fatal|panic)" !~ "(?i)level=(info|debug)"'), 24)], 10)
    return d


def host():
    d = Dash("wc-host", "Host hardware",
             "The k3s host (AMD Ryzen 7 7800X3D, NVMe + ZFS pool): CPU, memory, disks, ZFS, network and temperatures. "
             "Source: node_exporter built into Alloy (job node-exporter).")
    N = 'job="node-exporter"'
    d.row("At a glance")
    d.place([
        (d.stat("Uptime", f'time() - node_boot_time_seconds{{{N}}}', unit="s"), 3),
        (d.stat("CPU", f'1 - avg(rate(node_cpu_seconds_total{{{N},mode="idle"}}[5m]))', unit="percentunit",
                thresholds=[G, {"color": "orange", "value": 0.7}, {"color": "red", "value": 0.9}]), 3),
        (d.stat("Load / core", f'node_load5{{{N}}} / scalar(count(count by (cpu) (node_cpu_seconds_total{{{N}}})))', unit="short",
                thresholds=[G, {"color": "orange", "value": 0.8}, {"color": "red", "value": 1.5}]), 3),
        (d.stat("Memory used", f'1 - node_memory_MemAvailable_bytes{{{N}}} / node_memory_MemTotal_bytes{{{N}}}', unit="percentunit",
                thresholds=[G, {"color": "orange", "value": 0.8}, {"color": "red", "value": 0.92}]), 3),
        (d.stat("Root FS used", f'1 - node_filesystem_avail_bytes{{{N},mountpoint="/"}} / node_filesystem_size_bytes{{{N},mountpoint="/"}}',
                unit="percentunit", thresholds=[G, {"color": "orange", "value": 0.8}, {"color": "red", "value": 0.9}]), 3),
        (d.stat("ZFS pool online", f'min(node_zfs_zpool_state{{{N},state="online"}})',
                thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}],
                mappings=[{"type": "value", "options": {"1": {"text": "ONLINE"}, "0": {"text": "NOT ONLINE"}}}],
                desc="1 when every pool reports state online."), 3),
        (d.stat("Hottest sensor", f'max(node_hwmon_temp_celsius{{{N}}})', unit="celsius",
                thresholds=[G, {"color": "orange", "value": 65}, {"color": "red", "value": 80}]), 3),
        (d.stat("ARC hit ratio", f'rate(node_zfs_arc_hits{{{N}}}[5m]) / (rate(node_zfs_arc_hits{{{N}}}[5m]) + rate(node_zfs_arc_misses{{{N}}}[5m]))',
                unit="percentunit", thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 0.7}, {"color": "green", "value": 0.9}]), 3),
    ], 4)

    d.row("CPU and memory")
    d.place([
        (d.ts("CPU usage by mode",
              [(f'sum by (mode) (rate(node_cpu_seconds_total{{{N},mode!="idle"}}[5m])) / scalar(count(count by (cpu) (node_cpu_seconds_total{{{N}}})))', "{{mode}}")],
              unit="percentunit", stack=True, fill=40, maxv=1), 12),
        (d.ts("Load average",
              [(f'node_load1{{{N}}}', "1m"), (f'node_load5{{{N}}}', "5m"), (f'node_load15{{{N}}}', "15m"),
               (f'count(count by (cpu) (node_cpu_seconds_total{{{N}}}))', "cores")], desc="16 threads on this CPU."), 12),
    ], 8)
    d.place([
        (d.ts("Memory",
              [(f'node_memory_MemTotal_bytes{{{N}}} - node_memory_MemAvailable_bytes{{{N}}}', "used"),
               (f'node_memory_Cached_bytes{{{N}}} + node_memory_Buffers_bytes{{{N}}}', "cache + buffers"),
               (f'node_memory_MemFree_bytes{{{N}}}', "free"),
               (f'node_zfs_arc_size{{{N}}}', "ZFS ARC (inside used)")], unit="bytes"), 12),
        (d.ts("Swap and pressure (PSI)",
              [(f'node_memory_SwapTotal_bytes{{{N}}} - node_memory_SwapFree_bytes{{{N}}}', "swap used"),
               (f'rate(node_pressure_memory_waiting_seconds_total{{{N}}}[5m])', "memory stall (s/s)"),
               (f'rate(node_pressure_cpu_waiting_seconds_total{{{N}}}[5m])', "cpu stall (s/s)"),
               (f'rate(node_pressure_io_waiting_seconds_total{{{N}}}[5m])', "io stall (s/s)")]), 12),
    ], 8)

    d.row("ZFS")
    d.place([
        (d.ts("ARC size vs target",
              [(f'node_zfs_arc_size{{{N}}}', "size"), (f'node_zfs_arc_c{{{N}}}', "target (c)"), (f'node_zfs_arc_c_max{{{N}}}', "max")], unit="bytes"), 8),
        (d.ts("ARC hits / misses per second",
              [(f'rate(node_zfs_arc_hits{{{N}}}[5m])', "hits"), (f'rate(node_zfs_arc_misses{{{N}}}[5m])', "misses")], unit="ops"), 8),
        (d.table("Pool state",
                 f'node_zfs_zpool_state{{{N}}} == 1',
                 rename={"zpool": "Pool", "state": "State"}, hide=["Value", "instance", "job"]), 8),
    ], 8)

    d.row("Disks and filesystems")
    d.place([
        (d.bargauge("Filesystem used",
                    f'100 * (1 - node_filesystem_avail_bytes{{{N},fstype=~"ext4|zfs|vfat|xfs"}} / node_filesystem_size_bytes{{{N},fstype=~"ext4|zfs|vfat|xfs"}})',
                    "{{mountpoint}} ({{fstype}})", unit="percent",
                    thresholds=[G, {"color": "orange", "value": 80}, {"color": "red", "value": 90}], maxv=100), 12),
        (d.table("Filesystem free space",
                 f'node_filesystem_avail_bytes{{{N},fstype=~"ext4|zfs|vfat|xfs"}}',
                 unit="bytes", rename={"mountpoint": "Mount", "fstype": "Type", "device": "Device", "Value": "Free"},
                 hide=["instance", "job"], sort_by="Free"), 12),
    ], 8)
    d.place([
        (d.ts("Disk throughput",
              [(f'rate(node_disk_read_bytes_total{{{N}}}[5m])', "{{device}} read"),
               (f'-rate(node_disk_written_bytes_total{{{N}}}[5m])', "{{device}} write")], unit="Bps",
              desc="Writes are plotted below zero."), 12),
        (d.ts("Disk busy (IO utilisation)",
              [(f'rate(node_disk_io_time_seconds_total{{{N}}}[5m])', "{{device}}")], unit="percentunit", maxv=1), 12),
    ], 8)
    d.place([
        (d.ts("IOPS",
              [(f'rate(node_disk_reads_completed_total{{{N}}}[5m])', "{{device}} reads"),
               (f'rate(node_disk_writes_completed_total{{{N}}}[5m])', "{{device}} writes")], unit="iops"), 12),
        (d.ts("Average IO latency",
              [(f'rate(node_disk_read_time_seconds_total{{{N}}}[5m]) / rate(node_disk_reads_completed_total{{{N}}}[5m])', "{{device}} read"),
               (f'rate(node_disk_write_time_seconds_total{{{N}}}[5m]) / rate(node_disk_writes_completed_total{{{N}}}[5m])', "{{device}} write")], unit="s"), 12),
    ], 8)

    d.row("Network")
    d.place([
        (d.ts("Throughput",
              [(f'rate(node_network_receive_bytes_total{{{N},device!="lo"}}[5m])', "{{device}} rx"),
               (f'-rate(node_network_transmit_bytes_total{{{N},device!="lo"}}[5m])', "{{device}} tx")], unit="Bps"), 12),
        (d.ts("Errors and drops",
              [(f'rate(node_network_receive_errs_total{{{N},device!="lo"}}[5m])', "{{device}} rx errors"),
               (f'rate(node_network_transmit_errs_total{{{N},device!="lo"}}[5m])', "{{device}} tx errors"),
               (f'rate(node_network_receive_drop_total{{{N},device!="lo"}}[5m])', "{{device}} rx drops")], unit="pps"), 12),
    ], 8)
    d.place([
        (d.ts("TCP connections",
              [(f'node_netstat_Tcp_CurrEstab{{{N}}}', "established"), (f'node_sockstat_TCP_tw{{{N}}}', "time-wait")]), 12),
        (d.ts("Conntrack table",
              [(f'node_nf_conntrack_entries{{{N}}}', "entries"), (f'node_nf_conntrack_entries_limit{{{N}}}', "limit")]), 12),
    ], 8)

    d.row("Temperatures and system")
    d.place([
        (d.ts("Temperatures",
              [(f'node_hwmon_temp_celsius{{{N}}}', "{{chip}} {{sensor}}")], unit="celsius",
              desc="NVMe and ACPI sensors today. CPU (k10temp) needs a newer kernel; disk temperatures need the drivetemp module."), 12),
        (d.ts("Thermal zones",
              [(f'node_thermal_zone_temp{{{N}}}', "{{type}} {{zone}}")], unit="celsius"), 12),
    ], 8)
    d.place([
        (d.ts("Context switches and interrupts (per second)",
              [(f'rate(node_context_switches_total{{{N}}}[5m])', "context switches"), (f'rate(node_intr_total{{{N}}}[5m])', "interrupts")], unit="ops"), 12),
        (d.ts("File descriptors and processes",
              [(f'node_filefd_allocated{{{N}}}', "open files"), (f'node_procs_running{{{N}}}', "running procs"), (f'node_procs_blocked{{{N}}}', "blocked procs")]), 12),
    ], 8)
    return d


def resources():
    ns = var_query("namespace", "Namespace", 'label_values(kube_pod_info, k8s_namespace)')
    d = Dash("wc-resources", "Workload resources",
             "Per-pod CPU, memory, network and disk from cAdvisor, plus volume usage from the kubelet.", variables=[ns])
    sel = 'namespace=~"$namespace",container!="",container!="POD"'
    d.row("CPU and memory (actual use)")
    d.place([
        (d.ts("CPU by pod (cores)",
              [(f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{sel}}}[5m]))', "{{pod}}")], stack=True, fill=30), 12),
        (d.ts("Memory (working set) by pod",
              [(f'sum by (pod) (container_memory_working_set_bytes{{{sel}}})', "{{pod}}")], unit="bytes", stack=True, fill=30), 12),
    ], 9)
    d.place([
        (d.bargauge("Top 15 pods by CPU (now)",
                    f'topk(15, sum by (pod) (rate(container_cpu_usage_seconds_total{{{sel}}}[5m])))', "{{pod}}", unit="short"), 12),
        (d.bargauge("Top 15 pods by memory (now)",
                    f'topk(15, sum by (pod) (container_memory_working_set_bytes{{{sel}}}))', "{{pod}}", unit="bytes"), 12),
    ], 9)
    d.row("Use vs requests")
    d.place([
        (d.table("Memory use vs request (>1 means over)",
                 f'sum by (namespace, pod) (container_memory_working_set_bytes{{{sel}}}) / on (namespace, pod) group_left() '
                 f'sum by (namespace, pod) (label_replace(label_replace(kube_pod_container_resource_requests{{resource="memory"}}, "namespace", "$1", "k8s_namespace", "(.+)"), "pod", "$1", "k8s_pod_name", "(.+)"))',
                 rename={"namespace": "Namespace", "pod": "Pod", "Value": "Use / request"}, sort_by="Use / request"), 12),
        (d.ts("CPU throttling (share of periods throttled)",
              [(f'sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{{{sel}}}[5m])) / sum by (pod) (rate(container_cpu_cfs_periods_total{{{sel}}}[5m]))', "{{pod}}")],
              unit="percentunit"), 12),
    ], 9)
    d.row("Network and disk")
    d.place([
        (d.ts("Network by pod",
              [(f'sum by (pod) (rate(container_network_receive_bytes_total{{namespace=~"$namespace"}}[5m]))', "{{pod}} rx"),
               (f'-sum by (pod) (rate(container_network_transmit_bytes_total{{namespace=~"$namespace"}}[5m]))', "{{pod}} tx")], unit="Bps"), 12),
        (d.ts("Container disk IO",
              [(f'sum by (pod) (rate(container_fs_reads_bytes_total{{{sel}}}[5m]))', "{{pod}} read"),
               (f'-sum by (pod) (rate(container_fs_writes_bytes_total{{{sel}}}[5m]))', "{{pod}} write")], unit="Bps"), 12),
    ], 8)
    d.row("Volumes (PVCs) and OOM")
    d.place([
        (d.bargauge("PVC used (%)",
                    'topk(30, 100 * kubelet_volume_stats_used_bytes{namespace=~"$namespace"} / kubelet_volume_stats_capacity_bytes{namespace=~"$namespace"})',
                    "{{namespace}}/{{persistentvolumeclaim}}", unit="percent",
                    thresholds=[G, {"color": "orange", "value": 80}, {"color": "red", "value": 90}], maxv=100), 12),
        (d.table("PVC capacity and free space",
                 'kubelet_volume_stats_available_bytes{namespace=~"$namespace"}',
                 unit="bytes", rename={"namespace": "Namespace", "persistentvolumeclaim": "Claim", "Value": "Free"},
                 hide=["instance", "job", "node"], sort_by="Free"), 12),
    ], 9)
    d.place([
        (d.ts("OOM kills", [(f'sum by (pod) (increase(container_oom_events_total{{{sel}}}[10m]))', "{{pod}}")], stack=True, fill=40), 12),
        (d.ts("Kubelet running pods / containers",
              [('sum(kubelet_running_pods)', "pods"), ('sum(kubelet_running_containers)', "containers")]), 12),
    ], 8)
    return d


BUILDERS = [cluster_overview, apps, ingress, platform, host, resources]


def write_all():
    out = []
    for b in BUILDERS:
        d = b()
        path = os.path.join(HERE, f"{d.uid}.json")
        with open(path, "w") as f:
            json.dump(d.json(), f, indent=2)
            f.write("\n")
        out.append(path)
    return out


if __name__ == "__main__":
    for p in write_all():
        print("wrote", os.path.relpath(p))
