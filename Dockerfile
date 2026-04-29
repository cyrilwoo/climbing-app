FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync_calendar.py .

CMD exec functions-framework --target=sync_calendar --source=sync_calendar.py --port=$PORT
