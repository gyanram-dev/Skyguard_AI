#!/usr/bin/env bash
set -o errexit

echo "Installing Python dependencies..."
pip install -r requirements.txt

if [ -n "$ARTIFACT_URL" ]; then
    echo "Downloading artifacts from $ARTIFACT_URL ..."
    curl -L -s "$ARTIFACT_URL" -o artifacts.tar.gz
    echo "Extracting artifacts..."
    tar -xzf artifacts.tar.gz
    rm artifacts.tar.gz
    echo "Artifacts extracted."
else
    echo "WARNING: ARTIFACT_URL environment variable is not set. The backend may fail to start."
fi
