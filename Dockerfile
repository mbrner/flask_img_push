FROM python:3.9-slim-bullseye

# Set working directory
WORKDIR /root

# Copy the requirements.txt file and install Python dependencies
ADD requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
ADD start.py start.py
ADD slideshow slideshow
ADD entrypoint.sh entrypoint.sh

# Create necessary directories
RUN mkdir -p /root/Pictures/wedding /root/Database
ENV SLIDESHOW_IMG_DIR=/root/Pictures/wedding
COPY qrcode.jpg /root/Pictures/wedding/_placeholder_.jpg

# Make entrypoint script executable
RUN chmod +x /root/entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/root/entrypoint.sh"]
