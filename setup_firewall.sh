#!/bin/bash
# Firewall setup script for RunPod security
# Run with: sudo bash setup_firewall.sh

set -e

echo "Setting up firewall with ufw..."

# Install ufw if not present
apt-get update && apt-get install -y ufw

# Reset to defaults
ufw --force reset

# Default policies: deny incoming, allow outgoing
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (port 22) - critical for RunPod access
ufw allow 22/tcp

# Allow API server port (8000)
ufw allow 8000/tcp

# Allow RunPod's internal communication ports (if needed)
# RunPod uses various ports for their proxy system
ufw allow 8080/tcp

# Enable firewall
ufw --force enable

# Show status
echo ""
echo "Firewall enabled. Current rules:"
ufw status verbose

echo ""
echo "Firewall setup complete!"
