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

echo "⚠️  WARNING: Preparing release for $VERSION..."

# Warning check: warn if there are uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "🚨 Warning: You have uncommitted or unstaged changes in your repository!"
    read -p "Are you sure you want to proceed with release $VERSION? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "❌ Release aborted by user."
        exit 1
    fi
fi

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
