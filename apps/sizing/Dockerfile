FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir fastapi==0.118.0 uvicorn==0.37.0 pytest==8.4.2
COPY sizing ./sizing
COPY tests ./tests
# 빌드 시 계산 공식 테스트를 돌려, 실패하면 이미지가 만들어지지 않게 한다
RUN python -m pytest -q tests
USER 10001
EXPOSE 8000
CMD ["uvicorn", "sizing.main:app", "--host", "0.0.0.0", "--port", "8000"]
