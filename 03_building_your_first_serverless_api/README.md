# Project Setup
## Initialize project using CDK
```sh
mkdir product-api && cd product-api
cdk init app --language python

# Activate the project's virtual environment
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell

pip install -r requirements.txt
mkdir lambda_code
```