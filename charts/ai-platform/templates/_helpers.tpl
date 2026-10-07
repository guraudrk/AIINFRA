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

{{/* NetworkPolicy 출발지: 같은 네임스페이스의 앱 라벨 */}}
{{- define "np.from" -}}
- podSelector:
    matchLabels:
      app.kubernetes.io/name: {{ . }}
{{- end }}

{{/* NetworkPolicy 출발지: 다른 네임스페이스 전체 */}}
{{- define "np.fromNs" -}}
- namespaceSelector:
    matchLabels:
      kubernetes.io/metadata.name: {{ . }}
{{- end }}

{{/* 데이터 노드 배치 (nodeSelector + tolerations) */}}
{{- define "ai-platform.dataPlacement" -}}
nodeSelector:
  {{- toYaml .Values.dataNode.nodeSelector | nindent 2 }}
tolerations:
  {{- toYaml .Values.dataNode.tolerations | nindent 2 }}
{{- end }}
