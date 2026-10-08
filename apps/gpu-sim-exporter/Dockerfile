FROM python:3.12-slim
WORKDIR /app
COPY exporter.py .
USER 10001
EXPOSE 9400
CMD ["python", "exporter.py"]
