FROM python:3.7
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip install --upgrade pip
RUN pip install bel-commons
RUN pip install gunicorn
