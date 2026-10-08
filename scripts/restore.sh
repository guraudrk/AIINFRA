#!/usr/bin/env bash
# DB 복구: MinIO의 최신(또는 지정한) 백업을 내려받아 pg_restore 한다.
#   ./scripts/restore.sh                      최신 백업
#   BACKUP_KEY=postgres/hanbit-...dump ./scripts/restore.sh
# --clean --if-exists : 기존 객체를 지우고 백업 시점 상태로 되돌린다 (백업 이후 변경분은 사라진다 = RPO)
# --single-transaction: 복구 도중 실패하면 전부 롤백 (반쯤 복구된 상태를 남기지 않음)
set -euo pipefail
NS="${NS:-ai-platform}"
JOB="pg-restore-$(date +%s)"
PG_IMAGE=$(kubectl -n "$NS" get cronjob pg-backup -o jsonpath='{.spec.jobTemplate.spec.template.spec.initContainers[0].image}')
PY_IMAGE=$(kubectl -n "$NS" get cronjob pg-backup -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}')

kubectl -n "$NS" apply -f - >/dev/null <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: $JOB
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        app.kubernetes.io/name: pg-backup     # 백업과 같은 NetworkPolicy(DB·MinIO만)
    spec:
      restartPolicy: Never
      volumes:
        - { name: backup, emptyDir: {} }
        - { name: scripts, configMap: { name: backup-scripts } }
      initContainers:
        - name: download
          image: $PY_IMAGE
          command: ["python", "/scripts/download.py"]
          env:
            - { name: S3_ENDPOINT, value: "http://minio:9000" }
            - { name: BACKUP_BUCKET, value: "backups" }
            - { name: BACKUP_KEY, value: "${BACKUP_KEY:-}" }
            - name: S3_ACCESS_KEY
              valueFrom: { secretKeyRef: { name: minio-credentials, key: root-user } }
            - name: S3_SECRET_KEY
              valueFrom: { secretKeyRef: { name: minio-credentials, key: root-password } }
          volumeMounts:
            - { name: backup, mountPath: /backup }
            - { name: scripts, mountPath: /scripts }
      containers:
        - name: restore
          image: $PG_IMAGE
          command: ["sh", "-c"]
          args:
            - pg_restore -h postgres -U postgres -d hanbit --clean --if-exists --single-transaction
              /backup/restore.dump && echo '{"event":"restore_done"}'
          env:
            - name: PGPASSWORD
              valueFrom: { secretKeyRef: { name: postgres-credentials, key: postgres-password } }
          volumeMounts:
            - { name: backup, mountPath: /backup }
EOF
for _ in $(seq 1 100); do
  [[ "$(kubectl -n "$NS" get job "$JOB" -o jsonpath='{.status.succeeded}')" == "1" ]] && break
  if kubectl -n "$NS" get job "$JOB" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' | grep -q True; then
    echo "[restore] 실패"; kubectl -n "$NS" logs "job/$JOB" --all-containers --tail=30; exit 1
  fi
  sleep 3
done
kubectl -n "$NS" logs "job/$JOB" -c download
kubectl -n "$NS" logs "job/$JOB" -c restore | tail -1
