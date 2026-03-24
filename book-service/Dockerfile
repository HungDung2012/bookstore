FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app/

CMD ["sh", "-c", "python manage.py migrate && python seed_data.py && exec gunicorn book_service.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
