FROM python:3.7
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip install --upgrade pip
RUN pip install psycopg2-binary gunicorn
RUN pip install git+https://github.com/bel-commons/bel-commons.git@prepare-pybel-14

COPY . /app
WORKDIR /app
