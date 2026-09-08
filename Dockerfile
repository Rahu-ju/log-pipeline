# Use official Python base image
FROM python:3.12-slim
 
# Set working directory inside container
WORKDIR /app
 
# Copy requirements first (for better caching)
COPY requirements.txt .
 
# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy the rest of your app
COPY . .