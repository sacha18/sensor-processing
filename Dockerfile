FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline ./pipeline
COPY ui ./ui
COPY app.py ./
COPY .streamlit ./.streamlit
COPY sample_data ./sample_data

# mount a dataset at /data (any folder of <sensor_id>.json or <sensor_id>.csv
# files) to override the bundled sample_data/ fallback - see pipeline.resolve_data_dir()
ENV SENSOR_DATA_DIR=/data

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
