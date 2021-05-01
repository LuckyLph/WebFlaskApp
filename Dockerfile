FROM python:3.9.4-alpine3.13
ENV DB_HOST=host.docker.internal
ENV DB_PORT=5432
ENV DB_NAME=8inf349
ENV DB_USER=user
ENV DB_PASSWORD=pass
ENV FLASK_DEBUG=True
ENV FLASK_APP=8inf349
ADD 8inf349.py .
ADD models.py .
ADD services.py .
ADD products.sqlite .
ADD requirements.txt .
ENTRYPOINT python 8inf349.py
EXPOSE 5000
RUN apk update && apk add postgresql-dev gcc python3-dev musl-dev
RUN pip install -r requirements.txt