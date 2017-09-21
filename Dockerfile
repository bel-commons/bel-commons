FROM python:3.6.2
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip3 install pymysql
RUN pip3 install git+https://github.com/pybel/pybel.git@develop
RUN pip3 install git+https://github.com/pybel/pybel-tools.git@develop

ADD requirements.txt /
RUN pip3 install -r requirements.txt

COPY . /app
WORKDIR /app

RUN pip3 install .
