#!/bin/bash

if [ -z "$1" ]; then
    echo "❌ Error: Missing version number."
    echo "Usage: ./release.sh v1.X.X"
    exit 1
fi

if [[ "$1" != v* ]]; then
    echo "❌ Error: Version number must start with 'v' (e.g. v1.0.1)."
    echo "Usage: ./release.sh v1.X.X"
    exit 1
fi

VERSION=$1

echo "📦 Preparing release for $VERSION..."

# Ensure we are up to date and pushed first
git push origin master

# Create the tag
git tag $VERSION

# Push the tag to trigger GitHub Actions
git push origin $VERSION

echo "✅ Successfully pushed tag $VERSION!"
echo "🚀 GitHub Actions is now automatically building the zip/tar.gz files and publishing the release!"
echo "You can monitor the progress at: https://github.com/domedav/BloxDrive/actions"
