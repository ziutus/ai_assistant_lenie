#!/usr/bin/env bash

sudo apt-get update
sudo apt-get upgrade
sudo apt install unzip
sudo apt install python3
sudo apt install python-is-python3
sudo apt install python3.12-venv
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
ln -s /mnt/c/Users/ziutus/.aws/ .aws

sudo apt install jq more-utils

echo "installing python3-pip as it is needed for building lambda layers"
sudo apt install python3-pip

echo "Installing mc for easy play in console (for example checking lamda zip files"
sudo apt install mc


