#!/usr/bin/env bash
# 폐쇄망 흉내: 모든 kind 노드에서 "사설망이 아닌 목적지"로 나가는 패킷을 버린다.
#   - OUTPUT : 노드 자신(containerd 이미지 pull 등)
#   - FORWARD: 노드를 거쳐 나가는 Pod 트래픽
# 사설 대역(10/8, 172.16/12, 192.168/16)과 루프백은 허용 → 클러스터 내부 통신은 그대로.
#   ./scripts/block-egress.sh          차단
#   ./scripts/block-egress.sh undo     해제
set -euo pipefail
CLUSTER=ax-lab
MODE="${1:-block}"
for node in $(kind get nodes --name "$CLUSTER"); do
  for chain in OUTPUT FORWARD; do
    # 사설 대역은 RETURN 규칙으로 먼저 통과시키고, 나머지는 DROP (iptables는 ! -d 를 하나만 받음)
    if [[ "$MODE" == "undo" ]]; then
      while docker exec "$node" iptables -D "$chain" -m comment --comment airgap -j DROP 2>/dev/null; do :; done
      for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.0/8; do
        while docker exec "$node" iptables -D "$chain" -m comment --comment airgap -d "$net" -j RETURN 2>/dev/null; do :; done
      done
    else
      docker exec "$node" iptables -I "$chain" 1 -m comment --comment airgap -j DROP
      for net in 127.0.0.0/8 192.168.0.0/16 172.16.0.0/12 10.0.0.0/8; do
        docker exec "$node" iptables -I "$chain" 1 -m comment --comment airgap -d "$net" -j RETURN
      done
    fi
  done
  echo "[airgap] $node: $MODE"
done
