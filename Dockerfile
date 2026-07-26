# Verwende ein schlankes Python-Base-Image
FROM python:3.12-slim

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Kopiere Anwendungscode und SSL-Zertifikate
COPY certs ./certs
COPY server.py config.json index.html styles.css app.js ./

# HTTPS Port 2009 freigeben
EXPOSE 2009

# Umgebungsvariablen für Python-Unbuffered-Output
ENV PYTHONUNBUFFERED=1

# Starte den HTTPS Steuerungs-Server
CMD ["python", "server.py"]
