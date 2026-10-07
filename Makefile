# AX Platform Lab — 진입점. 각 타깃은 해당 모듈에서 채운다.
.PHONY: help up down deploy ingest backup restore chaos status

help:
	@echo "make up | down | deploy | ingest | backup | restore | chaos SCENARIO=N | status"

up:        ## M1: kind 클러스터 생성
	@echo "TODO(M1): scripts/cluster-up.sh"

down:      ## M1: kind 클러스터 삭제
	@echo "TODO(M1): scripts/cluster-down.sh"

deploy:    ## M2~: Helm 차트 배포
	@echo "TODO(M2): helm upgrade --install"

ingest:    ## M3: 문서 수집 Job 실행
	@echo "TODO(M3): apps/ingest Job"

backup:    ## M7: 즉시 백업
	@echo "TODO(M7): pg-backup"

restore:   ## M7: 최신 백업 복구
	@echo "TODO(M7): restore"

chaos:     ## M8: 장애 주입 (make chaos SCENARIO=1)
	@echo "TODO(M8): scripts/chaos/$(SCENARIO)"

status:    ## 클러스터 상태 요약
	@echo "TODO(M1): kubectl get nodes,pods -A"
