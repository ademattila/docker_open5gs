FROM ubuntu:jammy
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y \
        git \
        python3-pip \
        python3-setuptools \
        python3-pyscard \
        pcscd \
        libpcsclite-dev \
        iproute2 \
        net-tools \
        iputils-ping \
        tcpdump \
        sip-tester
RUN git clone https://github.com/herlesupreeth/SWu-IKEv2 && \
    cd SWu-IKEv2 && \
    pip3 list && \
    pip3 install -r requirements.txt
CMD ["/mnt/swu_client2/swu_client2_init.sh"]
