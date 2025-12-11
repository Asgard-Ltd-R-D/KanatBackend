FROM jenkins/jenkins:lts

USER root
RUN apt-get update && apt-get install -y lsb-release sudo curl gnupg

# Install Docker CLI inside Jenkins container
RUN curl -fsSL https://get.docker.com | sh

# Copy plugins.txt into Jenkins reference directory
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt

USER jenkins

# Install plugins listed in plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
