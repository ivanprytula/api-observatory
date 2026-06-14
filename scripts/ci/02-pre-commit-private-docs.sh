#!/bin/bash

# Pre-commit hook to prevent accidental files in learning_docs/
# This is a safety net in case the .gitignore entry is toggled.

FORBIDDEN_DIR="learning_docs/"

# Get list of staged files
STAGED_FILES=$(git diff --cached --name-only)

# Check if any staged file is in the forbidden directory
for FILE in $STAGED_FILES; do
    if [[ $FILE == "$FORBIDDEN_DIR"* ]]; then
        echo "❌ ERROR: You are trying to commit files in '$FORBIDDEN_DIR'."
        echo "These documents are intended for local planning and AI context only."
        echo "Please unstage them: git restore --staged $FORBIDDEN_DIR"
        exit 1
    fi
done

exit 0
