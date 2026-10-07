FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ingest.py .
# 비root 사용자로 실행
USER 10001
ENTRYPOINT ["python", "ingest.py"]
CMD ["all"]
