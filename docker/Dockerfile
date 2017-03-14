FROM python:3.6
MAINTAINER kozajaku@fit.cvut.cz

RUN set -ex \
	&& apt-get update && apt-get install git --no-install-recommends && rm -rf /var/lib/apt/lists/* \
	&& git clone https://github.com/kozajaku/spectraviewer.git spectraviewer \
	&& cd spectraviewer \
	&& python3 setup.py install \
	&& cd .. \
	&& rm -rf spectraviewer \
	&& apt-get purge -y --auto-remove git \
	&& rm -rf ~/.cache

RUN mkdir /tmp/filesystem \
    && mkdir /tmp/jobs

EXPOSE 7000

ENTRYPOINT ["spectraviewer"]