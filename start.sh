#!/bin/bash
while true; do
  ./venv/bin/python app.py
  EXIT_CODE=$?
  if [ $EXIT_CODE -ne 42 ]; then
    echo "Server exited with code $EXIT_CODE. Stopping."
    break
  fi
  echo "Restart requested. Restarting agent..."
  sleep 1
done
