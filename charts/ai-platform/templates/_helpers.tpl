{{/* 공통 라벨 */}}
{{- define "ai-platform.labels" -}}
app.kubernetes.io/part-of: ai-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/* GPU 노드 배치 (nodeSelector + tolerations) */}}
{{- define "ai-platform.gpuPlacement" -}}
nodeSelector:
  {{- toYaml .Values.gpuNode.nodeSelector | nindent 2 }}
tolerations:
  {{- toYaml .Values.gpuNode.tolerations | nindent 2 }}
{{- end }}

{{/* 데이터 노드 배치 (nodeSelector + tolerations) */}}
{{- define "ai-platform.dataPlacement" -}}
nodeSelector:
  {{- toYaml .Values.dataNode.nodeSelector | nindent 2 }}
tolerations:
  {{- toYaml .Values.dataNode.tolerations | nindent 2 }}
{{- end }}
