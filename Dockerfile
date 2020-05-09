FROM python:3.8
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip install --upgrade pip
RUN pip install git+https://github.com/pybel/pybel.git@3d46c69de95b36c4ff7fabede965e1e53d009d0f \
  && pip install git+https://github.com/pybel/pybel-tools.git \
  && pip install bio2bel

# Install requirements, which don't really change
COPY requirements.txt /tmp/
RUN pip install --requirement /tmp/requirements.txt

# Add and install BEL Commons code
COPY . /app
WORKDIR /app
RUN pip install .
# ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:5002", "bel_commons.wsgi:flask_app", "--log-level=INFO"]
