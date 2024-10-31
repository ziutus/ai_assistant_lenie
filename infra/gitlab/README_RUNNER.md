

## Preparing software on node

### Python pip

This project is using now Python 3.11, we should install it on server and change the default version:

```text
[root@ip-172-31-46-219 ai_assistant_lenie_server]# alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
[root@ip-172-31-46-219 ai_assistant_lenie_server]# alternatives --config python3

There is 1 program that provides 'python3'.

  Selection    Command
-----------------------------------------------
*+ 1           /usr/bin/python3.11

Enter to keep the current selection[+], or type selection number: 1

[root@ip-172-31-46-219 ai_assistant_lenie_server]# python3 --version
Python 3.11.6

```

We will need to install some Python packages, so we need pip command:
```shell
dnf install python3-pip
```

### go installer

```shell
sudo dnf update -y
sudo dnf install -y golang
```

In golang-bin you will find base pcommand go:

```text
[root@ip-172-31-46-219 ~]# rpm -qf /usr/bin/go
golang-bin-1.22.7-1.amzn2023.0.1.x86_64
```


## Instalation of test and syntax checker

### Python Flake8

```shell
pip3 install flake8-html
```

### Python pytest

```shell
pip install pytest-html
```

## Instalation of security tools

### semgrep

```shell
python3 -m pip install semgrep
python3 -m pip install --ignore-installed semgrep
```

### osv-scanner

and it can be used to install osv-scanner (latest version):

```bash
go install github.com/google/osv-scanner/cmd/osv-scanner@v1
```


