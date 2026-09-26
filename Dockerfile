FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt --break-system-packages

COPY . .

EXPOSE 5000
CMD ["python3", "devax_web.py"]
