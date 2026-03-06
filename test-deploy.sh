#!/bin/bash

# Simple test to check if we can run the deployment
echo "Testing deployment setup..."

# Check if we have required packages
echo "Checking for steamcmd..."
if command -v steamcmd &> /dev/null; then
    echo "steamcmd found"
else
    echo "steamcmd not found"
fi

# Check current user and permissions
echo "Current user: $(whoami)"
echo "Home directory: $HOME"

# Try to create a simple server directory
mkdir -p "$HOME/valheim-test/server"
if [ $? -eq 0 ]; then
    echo "Created test directory successfully"
else
    echo "Failed to create test directory"
fi

echo "Test complete"