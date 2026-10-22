{{/*
Expand the name of the chart.
*/}}
{{- define "bugtracker.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
If release name contains chart name it will be used as a full name.
*/}}
{{- define "bugtracker.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "bugtracker.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "bugtracker.labels" -}}
helm.sh/chart: {{ include "bugtracker.chart" . }}
app.kubernetes.io/name: {{ include "bugtracker.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels for one component (app | database).
Usage: include "bugtracker.selectorLabels" (dict "ctx" . "component" "app")
*/}}
{{- define "bugtracker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "bugtracker.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Name of the database resources.
*/}}
{{- define "bugtracker.dbName" -}}
{{- printf "%s-postgres" (include "bugtracker.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Application image. The tag is mandatory (commit SHA) — "latest" is not allowed.
*/}}
{{- define "bugtracker.image" -}}
{{- $tag := required "image.tag is required (use the commit SHA)" .Values.image.tag | toString }}
{{- if eq $tag "latest" }}
{{- fail "image.tag=latest is not allowed; use the commit SHA" }}
{{- end }}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "bugtracker.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "bugtracker.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
