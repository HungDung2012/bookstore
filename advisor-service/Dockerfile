FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --upgrade pip && \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu && \
    pip install -r requirements.txt

COPY . /app/

CMD ["sh", "-c", "python manage.py migrate && exec gunicorn advisor_service.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
