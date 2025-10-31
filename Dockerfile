# RunPod Serverless Docker Image for Chess Evaluation

FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04

# Set working directory
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy evaluation code
COPY handler.py .
COPY evaluate.py .

# Create volume mount point for persistent storage (dataset caching)
RUN mkdir -p /runpod-volume

# Set environment variable for RunPod
ENV PYTHONUNBUFFERED=1

# Handler function
CMD ["python", "-u", "handler.py"]
