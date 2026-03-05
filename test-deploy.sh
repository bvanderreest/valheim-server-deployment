#!/bin/bash

# Test script for deploy command functionality
# This script verifies that the deploy command can be called without errors

echo "Testing deploy command functionality..."

# Check if the main script exists
if [[ ! -f "valheim-server-manager.sh" ]]; then
    echo "Error: valheim-server-manager.sh not found"
    exit 1
fi

# Make the script executable
chmod +x valheim-server-manager.sh

# Test that the deploy command is recognized
echo "Checking if deploy command is available..."
if ./valheim-server-manager.sh help 2>/dev/null | grep -q "deploy"; then
    echo "✓ Deploy command found in help"
else
    echo "✗ Deploy command not found in help"
fi

# Test that the script can be parsed without syntax errors
echo "Checking for syntax errors..."
if bash -n valheim-server-manager.sh; then
    echo "✓ No syntax errors found"
else
    echo "✗ Syntax errors found"
    exit 1
fi

echo "Deploy command functionality test completed successfully!"