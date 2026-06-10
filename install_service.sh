#!/bin/bash
# Install script for Chess API systemd service
# Run with: sudo bash install_service.sh

set -e

echo "Installing Chess API systemd service..."

# Copy service file
cp /workspace/serverless_worker/chess-api.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable service to start on boot
systemctl enable chess-api.service

# Start the service now
systemctl start chess-api.service

# Show status
echo ""
systemctl status chess-api.service --no-pager

echo ""
echo "Service installed and started!"
echo "Commands:"
echo "  systemctl status chess-api    # Check status"
echo "  systemctl restart chess-api   # Restart"
echo "  systemctl stop chess-api      # Stop"
echo "  journalctl -u chess-api -f    # View logs"
