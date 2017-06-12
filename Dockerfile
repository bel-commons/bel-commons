FROM ubuntu:latest
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"
RUN apt-get update -y

# Install basic applications
RUN apt-get install -y tar git curl nano wget dialog net-tools build-essential

# Install python and basic python tools
RUN apt-get install -y python python-dev python-distribute python-pip

COPY . /app
WORKDIR /app

RUN pip install -r requirements.txt
RUN pip install .

# Expose ports
# EXPOSE 80

ENTRYPOINT ["python"]
CMD ["-m", "pybel_tools", "web", "--host", "0.0.0.0"]
