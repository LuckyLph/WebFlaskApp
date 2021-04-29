FROM python:3.9.4-alpine3.13
ADD work.py .
ADD 8inf349.py .
ADD models.py .
ADD services.py .
ADD products.sqlite .
ADD requirements.txt .
ENTRYPOINT python work.py
RUN pip install -r requirements.txt