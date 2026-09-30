#!/usr/bin/env bash
set -o errexit

echo "Installing Python dependencies..."
pip install -r requirements.txt

if [ -n "$ARTIFACT_URL" ]; then
    echo "Downloading artifacts from $ARTIFACT_URL ..."
    if ! curl -fL --retry 3 --retry-delay 2 "$ARTIFACT_URL" -o artifacts.tar.gz; then
        echo "Artifact download failed"
        exit 1
    fi
    
    if [ ! -f artifacts.tar.gz ]; then
        echo "Artifact validation failed: File not found"
        exit 1
    fi
    
    FILE_TYPE=$(file -b artifacts.tar.gz || echo "unknown")
    if [[ "$FILE_TYPE" != *"gzip compressed data"* ]] && [[ "$FILE_TYPE" != *"tar archive"* ]]; then
        echo "Artifact validation failed: Downloaded file is not a valid gzip/tar archive (Type: $FILE_TYPE)"
        echo "Contents of invalid file (head):"
        head -n 10 artifacts.tar.gz
        rm artifacts.tar.gz
        exit 1
    fi
    
    FILE_SIZE=$(stat -c%s artifacts.tar.gz 2>/dev/null || stat -f%z artifacts.tar.gz 2>/dev/null || echo 0)
    if [ "$FILE_SIZE" -lt 10000000 ]; then
        echo "Artifact validation failed: File size too small ($FILE_SIZE bytes). Expected ~38MB."
        rm artifacts.tar.gz
        exit 1
    fi

    echo "Extracting artifacts..."
    tar -xzf artifacts.tar.gz
    rm artifacts.tar.gz
    echo "Artifacts extracted."
else
    echo "WARNING: ARTIFACT_URL environment variable is not set. The backend may fail to start."
fi
