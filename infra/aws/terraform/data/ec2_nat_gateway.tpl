#!/bin/bash

sudo hostnamectl set-hostname ${new_hostname}
sudo yum -y update
sudo amazon-linux-extras install epel -y
sudo yum install gcc jemalloc-devel openssl-devel tcl tcl-devel -y
sudo wget http://download.redis.io/redis-stable.tar.gz
sudo tar xvzf redis-stable.tar.gz
cd redis-stable
sudo make BUILD_TLS=yes
sudo make install

# $ sudo yum -y install openssl-devel gcc
# $ wget http://download.redis.io/redis-stable.tar.gz
# $ tar xvzf redis-stable.tar.gz
# $ cd redis-stable
# $ make distclean
# $ make redis-cli BUILD_TLS=yes
# $ sudo install -m 755 src/redis-cli /usr/local/bin/

exit 0
