FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
RUN useradd -u 10001 -M pu && mkdir /dados && chown pu /dados
COPY ambiente/servidor.py /servidor.py
COPY app/public/ /site/
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "/servidor.py"]
