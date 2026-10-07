"""한빛정밀 문서 수집 파이프라인: MinIO → 청크 분할 → 임베딩 → pgvector.

모드
  upload      로컬 폴더(/src/docs, /src/csv)를 MinIO raw-docs 버킷에 올린다 (버킷이 없으면 생성)
  structured  raw-docs/csv/*.csv 를 정형 테이블에 적재 (트랜잭션 안에서 비우고 다시 채움)
  docs        raw-docs/docs/*.md 를 청크·임베딩해 적재. 내용 해시가 같으면 건너뛴다(변경분만)
  all         structured + docs

설정은 모두 환경변수로 받는다 (비밀번호는 Kubernetes Secret에서 주입).
"""
import csv
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import boto3
import psycopg

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
BUCKET = os.environ.get("RAW_BUCKET", "raw-docs")
EXTRA_BUCKETS = [b for b in os.environ.get("EXTRA_BUCKETS", "backups").split(",") if b]
EMBED_URL = os.environ.get("EMBED_URL", "http://embedding-serving:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
EMBED_BATCH = int(os.environ.get("EMBED_BATCH", "16"))
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "100"))

# 외래키 순서대로 적재 (부모 테이블 먼저)
CSV_TABLES = ["equipment", "alarm_codes", "parts", "stock", "maintenance_history",
              "alarm_parts", "alarm_documents"]


def log(event, **kw):
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **kw}, ensure_ascii=False), flush=True)


def s3():
    return boto3.client("s3", endpoint_url=S3_ENDPOINT,
                        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
                        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
                        region_name="us-east-1")


def db():
    return psycopg.connect(host=os.environ.get("PGHOST", "postgres"), dbname=os.environ.get("PGDATABASE", "hanbit"),
                           user=os.environ.get("PGUSER", "ax_ingest"), password=os.environ["PGPASSWORD"])


# ── upload ──────────────────────────────────────────────────
def upload(src="/src"):
    client = s3()
    existing = {b["Name"] for b in client.list_buckets()["Buckets"]}
    for bucket in [BUCKET, *EXTRA_BUCKETS]:
        if bucket not in existing:
            client.create_bucket(Bucket=bucket)
            log("bucket_created", bucket=bucket)
    count = 0
    for sub in ("docs", "csv"):
        # ConfigMap 마운트에는 ..data 같은 숨김 링크가 있으므로 일반 파일만 올린다
        for path in sorted(Path(src, sub).glob("[!.]*")):
            client.upload_file(str(path), BUCKET, f"{sub}/{path.name}")
            count += 1
    log("upload_done", bucket=BUCKET, objects=count)


# ── structured ──────────────────────────────────────────────
def load_structured():
    client = s3()
    with db() as conn, conn.cursor() as cur:
        # 자식 테이블부터 비운다. 하나의 트랜잭션이라 실패하면 전부 되돌아간다
        cur.execute("TRUNCATE " + ", ".join(reversed(CSV_TABLES)))
        for table in CSV_TABLES:
            body = client.get_object(Bucket=BUCKET, Key=f"csv/{table}.csv")["Body"].read().decode("utf-8")
            cols = ", ".join(next(csv.reader(io.StringIO(body))))
            # RLS가 켜진 테이블에는 COPY를 직접 쓸 수 없다(M4 이후 maintenance_history).
            # 임시 테이블에 COPY로 빠르게 넣고 INSERT ... SELECT 로 옮기면 RLS 정책을 그대로 거친다.
            cur.execute(f"CREATE TEMP TABLE tmp_load (LIKE {table}) ON COMMIT DROP")
            with cur.copy(f"COPY tmp_load ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
                cp.write(body)
            cur.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM tmp_load")
            log("table_loaded", table=table, rows=cur.rowcount)
            cur.execute("DROP TABLE tmp_load")


# ── docs ────────────────────────────────────────────────────
def parse_markdown(text):
    """앞부분 '---' 메타데이터와 본문을 분리한다 (YAML 라이브러리 없이 key: value만)."""
    _, meta_block, body = text.split("---", 2)
    meta = dict(line.split(": ", 1) for line in meta_block.strip().splitlines())
    return meta, body.strip()


def split_sections(body):
    """## / ### 제목 단위로 나눈다. 반환: [(섹션 제목, 내용)]"""
    sections, title, buf = [], "개요", []
    for line in body.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            if "".join(buf).strip():
                sections.append((title, "\n".join(buf).strip()))
            title, buf = line.lstrip("#").strip(), []
        elif not line.startswith("# "):
            buf.append(line)
    if "".join(buf).strip():
        sections.append((title, "\n".join(buf).strip()))
    return sections


def chunk_document(meta, body):
    """섹션이 CHUNK_SIZE를 넘으면 CHUNK_OVERLAP만큼 겹치게 자른다. 각 청크 앞에 [문서 > 섹션] 맥락을 붙인다."""
    chunks = []
    for section, content in split_sections(body):
        step = CHUNK_SIZE - CHUNK_OVERLAP
        start = 0
        while True:
            piece = content[start:start + CHUNK_SIZE]
            chunks.append((section, f"[{meta['title']} > {section}]\n{piece}"))
            if start + CHUNK_SIZE >= len(content):
                break
            start += step
    return chunks


def embed(texts):
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):
        req = urllib.request.Request(f"{EMBED_URL}/api/embed",
                                     data=json.dumps({"model": EMBED_MODEL, "input": texts[i:i + EMBED_BATCH]}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            batch = json.load(resp)["embeddings"]
        if len(batch[0]) != EMBED_DIM:
            # 모델과 DB 컬럼 차원이 다르면 적재해도 검색이 불가능하다 → 즉시 실패시켜 알린다
            raise RuntimeError(f"임베딩 차원 불일치: 모델 {EMBED_MODEL}={len(batch[0])}, 설정 EMBED_DIM={EMBED_DIM}")
        vectors.extend(batch)
    return vectors


def to_vector(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def load_docs():
    client = s3()
    keys = [o["Key"] for o in client.list_objects_v2(Bucket=BUCKET, Prefix="docs/").get("Contents", [])]
    stats = {"total": len(keys), "updated": 0, "skipped": 0, "chunks": 0}
    with db() as conn:
        seen = []
        for key in keys:
            text = client.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8")
            meta, body = parse_markdown(text)
            seen.append(meta["doc_id"])
            digest = hashlib.sha256(text.encode()).hexdigest()
            row = conn.execute("SELECT content_hash FROM documents WHERE doc_id = %s", (meta["doc_id"],)).fetchone()
            if row and row[0] == digest:
                stats["skipped"] += 1
                continue
            chunks = chunk_document(meta, body)
            vectors = embed([c[1] for c in chunks])
            with conn.transaction():  # 문서 하나 단위로 원자적 교체
                conn.execute("DELETE FROM documents WHERE doc_id = %s", (meta["doc_id"],))  # 청크는 CASCADE 삭제
                conn.execute("""INSERT INTO documents (doc_id, title, dept, access_level, version, equipment_id,
                                                       source_key, content_hash)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                             (meta["doc_id"], meta["title"], meta["dept"], meta["access_level"], meta["version"],
                              meta.get("equipment_id"), key, digest))
                with conn.cursor() as cur:
                    cur.executemany("""INSERT INTO chunks (doc_id, chunk_index, section, content, embedding,
                                                           access_level, dept)
                                       VALUES (%s, %s, %s, %s, %s::vector, %s, %s)""",
                                    [(meta["doc_id"], i, sec, content, to_vector(vec), meta["access_level"], meta["dept"])
                                     for i, ((sec, content), vec) in enumerate(zip(chunks, vectors))])
            stats["updated"] += 1
            stats["chunks"] += len(chunks)
            log("doc_ingested", doc_id=meta["doc_id"], version=meta["version"], chunks=len(chunks))
        # 버킷에서 사라진 문서는 DB에서도 지운다
        removed = conn.execute("DELETE FROM documents WHERE NOT (doc_id = ANY(%s)) RETURNING doc_id", (seen,)).fetchall()
        stats["removed"] = len(removed)
    log("docs_done", **stats)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "upload":
        upload()
    elif mode == "structured":
        load_structured()
    elif mode == "docs":
        load_docs()
    elif mode == "all":
        load_structured()
        load_docs()
    else:
        sys.exit(f"알 수 없는 모드: {mode}")
