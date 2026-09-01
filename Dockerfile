# Use an official Python runtime as a parent image
FROM python:3.14-slim

# Set the working directory in the container
WORKDIR /app

# Prevent Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Copy project files for installation
COPY pyproject.toml README.md /app/

RUN mkdir /app/src

# Install dependencies (all are now in pyproject.toml, no need to repeat)
RUN pip install --no-cache-dir .

COPY src /app/src
COPY scheduler /app/scheduler

# Run main.py when the container launches
CMD ["python", "-m", "src.main"]