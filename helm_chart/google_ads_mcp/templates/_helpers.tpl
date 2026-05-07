{{/*
Expand the name of the chart.
*/}}
{{- define "google-ads-mcp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncated to 63 chars because some Kubernetes name fields have limits.
*/}}
{{- define "google-ads-mcp.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label value (chart name + version).
*/}}
{{- define "google-ads-mcp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "google-ads-mcp.labels" -}}
helm.sh/chart: {{ include "google-ads-mcp.chart" . }}
{{ include "google-ads-mcp.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "google-ads-mcp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "google-ads-mcp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Image reference — repository:tag. Fails early when tag is empty.
*/}}
{{- define "google-ads-mcp.image" -}}
{{- if not .Values.image.tag }}
{{- fail "image.tag is required — set --set image.tag=<TAG> or pin it in values.yaml" }}
{{- end }}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag }}
{{- end }}

{{/*
ServiceAccount name to use.
*/}}
{{- define "google-ads-mcp.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "google-ads-mcp.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
