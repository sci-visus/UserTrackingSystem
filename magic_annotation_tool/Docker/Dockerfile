FROM python:3.11-slim

# Install system dependencies for OpenSlide
RUN apt-get update && apt-get install -y \
    openslide-tools \
    libopenjp2-7 \
    libtiff6 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /main_app

# Disable Python output buffering
ENV PYTHONUNBUFFERED=1

# Copy requirements file
COPY Docker/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY Features/ ./Features/
COPY Docker/start.sh .

# Expose ports for Panel app and Flask tile server
EXPOSE 10565
EXPOSE 10566

# Run both servers using start script
CMD ["bash", "start.sh"]