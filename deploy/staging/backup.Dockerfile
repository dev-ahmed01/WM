FROM postgres:16-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3 age \
  && rm -rf /var/lib/apt/lists/*
COPY scripts/backup_postgres_encrypted.py /usr/local/bin/workmate_backup.py
ENTRYPOINT ["python3", "/usr/local/bin/workmate_backup.py"]
