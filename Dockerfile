FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY price_watch ./price_watch
COPY watchlist.json .
# no reason for a web api to run as root; the volume dir has to be its own
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
ENV DB_PATH=/data/price_watch.db
VOLUME /data
EXPOSE 8000
CMD ["waitress-serve", "--port=8000", "price_watch.api:app"]
