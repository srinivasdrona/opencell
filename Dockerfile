FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY opencell/ opencell/

RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

CMD ["pytest"]
