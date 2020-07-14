FROM python:3.8
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

# Install requirements, which don't really change
COPY requirements.txt /tmp/
RUN pip install --upgrade pip \
  && pip install --requirement /tmp/requirements.txt

RUN pip install --upgrade pip \
  && pip install git+https://github.com/pybel/pybel.git@ec412d1a574ef67929c588eca4f6d9f73a453cc5 \
  && pip install git+https://github.com/bio2bel/bio2bel.git@9d058a2a14723bd1096785cb7bd1fefb2e2e273b \
  && pip install git+https://github.com/pybel/pybel-tools.git@63cb84823b45fb823e3afe3817d123270d6a8a04

# Add and install BEL Commons code
COPY . /app
WORKDIR /app
RUN pip install .
# ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:5002", "bel_commons.wsgi:flask_app", "--log-level=INFO"]
