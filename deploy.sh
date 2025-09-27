#!/bin/bash

if [[ $# -eq 0 ]] ; then
  echo 'usage: ./deploy.sh customer stage'
  exit 1
fi

npm install
poetry install
npx serverless deploy -s $1-$2 --param="customer=$1" --param="stage=$2"
