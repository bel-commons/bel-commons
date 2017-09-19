FROM python:3.6.2
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip3 install pymysql
RUN pip3 install git+https://github.com/pybel/pybel.git@develop
RUN pip3 install git+https://github.com/pybel/pybel-tools.git@cf17785d881d87e9a99bc5988f4e6a9a721fd13a

ADD requirements.txt /
RUN pip3 install -r requirements.txt

COPY . /app
WORKDIR /app

RUN pip3 install .
