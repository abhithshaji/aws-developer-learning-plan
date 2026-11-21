#!/bin/bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate 
pip install -r requirements.txt
pip install -r requirements-dev.txt

mkdir -p layers/pydantic/python
pip install \
  --platform manylinux2014_x86_64 \
  --target layers/pydantic/python \
  --implementation cp \
  --python-version 3.13 \
  --only-binary=:all: \
  --no-cache-dir \
  pydantic