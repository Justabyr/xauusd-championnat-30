FROM python:3.12-slim
WORKDIR /app
COPY championship.py .
CMD ["python","-u","championship.py"]
