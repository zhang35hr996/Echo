FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY echo ./echo
COPY web ./web
ENV ECHO_DB_PATH=/data/echo.db
EXPOSE 8080
CMD ["uvicorn", "echo.api:app", "--host", "0.0.0.0", "--port", "8080"]
