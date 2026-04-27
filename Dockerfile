FROM ubuntu:latest
LABEL authors="polat"

ENTRYPOINT ["top", "-b"]