FROM python:3.11-slim

WORKDIR /app

# Game times are stored as naive local times, so the container must run in the
# players' time zone (set TZ, see docker-compose.yml)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p instance

ENV FLASK_DEBUG=0
ENV TZ=Europe/Berlin

EXPOSE 5000

CMD ["sh", "-c", "flask db upgrade && python app.py"]
