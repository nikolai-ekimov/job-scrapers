# 1. Use an official Python runtime as a parent image
FROM python:3.13.5-slim-bookworm

# 2. Set DEBIAN_FRONTEND to noninteractive to avoid prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# 3. Install system dependencies and Google Chrome in a single layer for a smaller image
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    unzip \
    # Required Chrome dependencies
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 && \
    # Add Google's official GPG key
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome-keyring.gpg && \
    # Set up the repository
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    # Update apt and install Chrome from the repository
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    # Clean up to keep the image size down
    rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/apt/sources.list.d/google-chrome.list

# 4. Create a non-root user for better security
RUN useradd --create-home dockie
USER dockie
WORKDIR /home/dockie/

ENV PATH="/home/dockie/.local/bin:${PATH}"

# 5. Copy requirements first to leverage Docker layer caching
COPY --chown=dockie:dockie requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application files
COPY --chown=dockie:dockie ./app_uw/ /home/dockie/app_uw/
COPY --chown=dockie:dockie ./app_li/ /home/dockie/app_li/

# 7. Install the correct chromedriver for the installed Chrome version
# This will be installed in the user's home directory, and seleniumbase will find it.
RUN python -m seleniumbase install chromedriver
