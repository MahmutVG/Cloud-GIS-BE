ARG FUNCTION_DIR="/function"
FROM osgeo/gdal:ubuntu-small-3.6.3

# Update GPG keys and install packages
RUN apt-get update && \
    apt-get install -y gnupg && \
    apt-key update && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python and pip with proper cleanup
RUN apt-get update && \
    apt-get install -y \
    python3 \
    python3-pip \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR ${FUNCTION_DIR}

# Copy and install requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY sentinel_data.py .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sentinel_data.handler"]