FROM python:3.9.4-alpine3.13
ADD work.py .
ADD models.py .
ADD services.py .
ADD products.sqlite .
ADD requirements.txt .
ENTRYPOINT python work.py
EXPOSE 5000
RUN apk update && apk add postgresql-dev gcc python3-dev musl-dev
RUN pip install -r requirements.txt