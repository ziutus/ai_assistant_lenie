# Step into Script Execution with Error Handling
$ErrorActionPreference = "Stop"

# Remove tmp/lenie_openai directory if exists and create new one 
Remove-Item -Recurse -Force tmp/lenie_openai -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path tmp/lenie_openai

# Change directory to tmp/lenie_openai
Set-Location -Path tmp/lenie_openai

# Print working directory
Write-Host (Get-Location)

# Create python directory
New-Item -ItemType Directory -Force -Path ./python

# Pip install openai
python -m pip install 'openai' --platform 'manylinux2014_x86_64' --python-version '3.11' --only-binary=:all: -t './python'

# Archive python directory
Compress-Archive -Path ./python -DestinationPath ./lenie_openai.zip

# Now we can upload our layer to AWS Lambda
aws lambda publish-layer-version --layer-name lenie_openai --zip-file fileb://./lenie_openai.zip --compatible-runtimes python3.11 --profile stalker-free-developer

# Remove tmp/lenie directory
Remove-Item -Recurse -Force tmp/lenie -ErrorAction SilentlyContinue