FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (needed for OpenCV and PIL)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
# Install PyTorch CPU first to save size if needed, but requirements.txt might have it
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose port
EXPOSE 8003

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
