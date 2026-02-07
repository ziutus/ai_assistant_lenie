# Virtual Machine Setup

Instructions for setting up the Lenie application on a virtual Linux machine.

> **Parent document:** [../README.md](../README.md) — project overview.

## Debian Machine

```bash
useradd lenie-ai
mkdir /home/lenie-ai
chown lenie-ai:lenie-ai /home/lenie-ai/

apt-get install git
apt install python3.11-venv
apt install python3-pip

```

Installation of PostgreSQL database

```bash

```

```bash
python3 server.py
```
