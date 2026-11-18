FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DADOS=/dados
WORKDIR /app
RUN groupadd -g 10001 enem && useradd -u 10001 -g enem -M enem && mkdir /dados && chown enem:enem /dados
COPY --chown=enem:enem app/ /app/
USER 10001:10001
EXPOSE 8000
CMD ["python", "servidor.py"]
