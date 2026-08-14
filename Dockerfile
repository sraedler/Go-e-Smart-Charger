# Verwende ein schlankes Python-Base-Image
FROM python:3.12-slim

# Installiere Zertifikate und Zeitzonen für zuverlässige HTTPS-Abrufe (SolarEdge & VKW)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Umgebungsvariablen für Python-Unbuffered-Output
ENV PYTHONUNBUFFERED=1

# Kopiere Anwendungsdateien
COPY . /app

# Port 2009 freigeben
EXPOSE 2009

# Starte den PV Steuerungs-Server
CMD ["python", "server.py"]
