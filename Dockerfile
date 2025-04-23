FROM python:latest
LABEL authors="alexander"

COPY ./requirements.txt /requirements.txt

WORKDIR /
RUN pip3 install -r requirements.txt

COPY . /

ENTRYPOINT ["python3", "main.py"]
