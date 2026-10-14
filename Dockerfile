FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema para Chromium/Playwright
RUN apt-get update && apt-get install -y \
    libnss3 \
    libxss1 \
    libappindicator1 \
    libindicator7 \
    libasound2 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgam1 \
    libgcc1 \
    libgconf-2-4 \
    libgdk-pixbuf1.0-0 \
    libglib2.0-0 \
    libgtk-3-0 \
    libharfbuzz0b \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    libxslt1.1 \
    libxt6 \
    fonts-liberation \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*\n\n# Copiar requirements.txt\nCOPY requirements.txt .\n\n# Instalar dependências Python\nRUN pip install --no-cache-dir -r requirements.txt\n\n# Instalar Playwright browsers\nRUN playwright install chromium\n\n# Copiar código da aplicação\nCOPY servidor.py .\nCOPY interface ./interface\n\n# Definir porta\nEXPOSE 8080\n\nENV PORT=8080\n\nCMD [\"python\", \"servidor.py\"]\n