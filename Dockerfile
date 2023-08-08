FROM continuumio/miniconda3:23.5.2-0 as build

USER root
WORKDIR /root

# prepare conda environment
ADD requirements.yml requirements.yml
RUN conda env create -f requirements.yml
RUN conda install -c conda-forge conda-pack
RUN conda-pack -n flask_image_gallery -o /tmp/env.tar --ignore-missing-files && \
    mkdir /venv \
    && cd /venv \
    && tar xf /tmp/env.tar \
    && rm /tmp/env.tar
RUN /venv/bin/conda-unpack

FROM debian:bullseye-20220801-slim as runtime

USER root
WORKDIR /root

RUN apt-get update && apt-get upgrade -y 

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# copy virtual env and scripts
COPY --from=build /venv /venv

ADD start.py start.py
ADD slideshow slideshow
ADD entrypoint.sh .

RUN mkdir Pictures && cd Pictures && mkdir wedding

RUN mkdir Database 

RUN chmod 555 /root/entrypoint.sh

ENTRYPOINT ["/root/entrypoint.sh"]