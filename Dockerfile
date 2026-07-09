FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app.py config.py logging_config.py models.py normalize.py oci_client.py ./

RUN pip install --no-cache-dir .

EXPOSE 8501

CMD ["streamlit", "run", "app.py"]
