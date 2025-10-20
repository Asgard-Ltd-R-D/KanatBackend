#The base image of QuestDB
FROM questdb/questdb:latest

#Install curl to use in the healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
