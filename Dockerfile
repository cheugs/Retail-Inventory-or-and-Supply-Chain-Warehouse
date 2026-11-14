# Live online dashboard (Render, Koyeb...): FastAPI server reading the hosted
# warehouse given by DATABASE_URL (for example a free Neon database).
# If the database cannot be reached, it serves the saved snapshot instead.
# The full local stack does not use this file (see docker-compose.yml).
FROM python:3.12-slim
WORKDIR /app
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dashboard/ ./dashboard/
ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
# most free hosts give the port in $PORT
CMD ["sh", "-c", "uvicorn dashboard.app:app --host 0.0.0.0 --port ${PORT}"]
