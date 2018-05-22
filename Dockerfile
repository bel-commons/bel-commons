FROM python:3.6.2
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip3 install --upgrade pip
RUN pip3 install mysqlclient
RUN pip3 install pandas==0.20.3
RUN pip3 install git+https://github.com/pybel/pybel.git@develop
RUN pip3 install git+https://github.com/pybel/pybel-tools.git@develop

ADD requirements.txt /
RUN pip3 install -r requirements.txt

COPY . /app
WORKDIR /app

RUN pip3 install .
