FROM python:3.8
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip install --upgrade pip

# Install requirements, which don't really change
COPY requirements.txt /tmp/
RUN pip install --requirement /tmp/requirements.txt

RUN pip install git+https://github.com/pybel/pybel.git@6861346855e9ace4ddb7e64d1309daf6f630ba2e \
  && pip install git+https://github.com/pybel/pybel-tools.git@5afd10987a5367b43061047354d998ffe333cecf \
  && pip install bio2bel

# Add and install BEL Commons code
COPY . /app
WORKDIR /app
RUN pip install .
# ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:5002", "bel_commons.wsgi:flask_app", "--log-level=INFO"]
