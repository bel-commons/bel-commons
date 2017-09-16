FROM ubuntu:latest
#FROM python:3.4-alpine
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"
RUN apt-get update -y
RUN apt-get install -y apt-utils
RUN apt-get install -y tar git curl nano wget dialog net-tools build-essential
RUN apt-get install -y python3 python3-dev python-distribute python3-pip

COPY . /app
WORKDIR /app

RUN pip3 install .
RUN pip3 install -U "celery[redis]"
RUN pip3 install gunicorn
