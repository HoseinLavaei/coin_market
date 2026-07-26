# Use an official Python runtime as a parent image
FROM python:3.14-slim

# Set the working directory in the container
WORKDIR /app

# Prevent Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Copy only the necessary files for installation first to leverage Docker cache
COPY pyproject.toml README.md /app/
COPY src /app/src

# Install dependencies and the project
RUN pip install --no-cache-dir . httpx python-dotenv python-telegram-bot sqlalchemy asyncpg

# Copy the rest of the files (like .env if needed, though compose handles it)
COPY . /app

# Run main.py when the container launches
CMD ["python", "src/main.py"]
