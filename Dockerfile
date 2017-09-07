FROM ubuntu:latest
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"
RUN apt-get update -y

# Install basic applications
RUN apt-get install -y tar git curl nano wget dialog net-tools build-essential

# Install python and basic python tools
RUN apt-get install -y python python-dev python-distribute python-pip

COPY . /app
WORKDIR /app

RUN pip install -r requirements.txt
RUN pip install .
RUN pip install gunicorn

RUN apt-get install -y rabbitmq-server
CMD service rabbitmq-server start

EXPOSE 8000

CMD celery worker -A pybel_web.celery_worker.celery --detach

CMD gunicorn -b "0.0.0.0:8000" pybel_web.run:app
