FROM python:3.8
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip install --upgrade pip

# Install requirements, which don't really change
COPY requirements.txt /tmp/
RUN pip install --requirement /tmp/requirements.txt

RUN pip install git+https://github.com/pybel/pybel.git@dea6bfc732558c5f034040a28a08b3b727d5f937 \
  && pip install git+https://github.com/pybel/pybel-tools.git \
  && pip install bio2bel

# Add and install BEL Commons code
COPY . /app
WORKDIR /app
RUN pip install .
# ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:5002", "bel_commons.wsgi:flask_app", "--log-level=INFO"]
