FROM python:3.12-slim

WORKDIR /app

COPY scripts/ /app/scripts/
COPY db/ /app/db/

ENV VITALS_DB_PATH=/app/data/vitals.db

CMD ["sh", "-c", "python /app/scripts/seed_patients.py && python /app/scripts/generate_vitals_stream.py --interval 1 --anomaly-rate 0.12"]
