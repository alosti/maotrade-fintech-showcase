# Docker Architecture - MAOTrade Container

Documentazione per build e deploy del container MAOTrade.

## Immagine Base e Dipendenze

**Base**: `python:3.11-slim`
- Bilanciamento tra funzionalità e dimensioni
- Python 3.11 per miglioramenti performance
- Variant slim per footprint ridotto

**Dipendenze Sistema**:
```dockerfile
build-essential    # Compilazione extension Python native
libssl-dev         # Connessioni SSL per broker APIs  
libffi-dev         # Librerie crittografiche
python3-dev        # Header Python per extensions
cargo              # Rust toolchain (dipendenze Python moderne)
tzdata             # Timezone Europe/Rome per orari trading
```

## Strategia Configurazione

### Gerarchia File
```
config/maotrade.ini           # Configurazione base
config/mt_docker_config.ini   # Override per Docker  
mt_user_config.ini            # Config finale (copia da docker config)
```

### Variabili Ambiente
Il container usa 12 variabili ambiente per configurazione runtime:

#### Controllo Logging
```bash
LOG_LEVEL=info              # debug|info|warning|error
LOG_CONFIG=false            # Mostra config all'avvio
LOG_QUERY=false             # Log query database
PUSH_NOTIFY=false           # Abilita notifiche push
```

#### Servizi Esterni
```bash
FLUENTD_ENABLE=true         # Aggregazione log
FLUENTD_HOST=host.docker.internal
FLUENTD_LEVEL=info
```

#### Trading Engine
```bash
TRADING_ENABLE=true         # Switch master trading
DAILY_CLEAN_TIME=23:45      # Finestra manutenzione
```

#### API e Database (iniettate a runtime)
```bash
WS_BASEURL=https://service.maotrade.it/maoapi
WS_SSL_VERIFY=true
DB_HOSTNAME=${DB_HOSTNAME}
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=${DB_NAME}
ACCOUNT_ID=${ACCOUNT_ID}
```

## Build e Deploy

### Build Immagine
```bash
docker build -t maotrade:latest .
```

### Esecuzione Container
```bash
docker run -d \
  --name maotrade \
  -p 2260:2260 \
  -e DB_HOSTNAME=localhost \
  -e DB_PASSWORD=tua_password \
  -e DB_NAME=mt_trading \
  -e ACCOUNT_ID=12345 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  maotrade:latest
```

### Esempi Override Ambiente
```bash
# Modalità debug
docker run -e LOG_LEVEL=debug -e LOG_QUERY=true maotrade:latest

# Disabilita trading (solo recupero dati storici dai broker)
docker run -e TRADING_ENABLE=false maotrade:latest

# Endpoint API custom
docker run -e WS_BASEURL=https://test-api.example.com maotrade:latest
```

## Gestione Container

### Log
```bash
# Log applicazione
docker logs maotrade

# Follow real-time
docker logs -f maotrade

# Accesso file log
docker exec -it maotrade tail -f /app/logs/log-out.log
```

### Health Check
```bash
# Stato container
docker ps | grep maotrade

# Connettività porta
curl http://localhost:2260/health
```

### Stop/Start
```bash
# Stop graduale
docker stop maotrade

# Kill forzato
docker kill maotrade

# Restart
docker restart maotrade
```

## Mount Volumi

### Mount Richiesti
```bash
-v $(pwd)/logs:/app/logs        # Persistenza log
-v $(pwd)/data:/app/data        # Cache dati/file temporanei
```

### Mount Opzionali
```bash
-v $(pwd)/config:/app/config:ro # Override configurazione custom
```

## Note Sicurezza

- Credenziali database solo via environment
- Singola porta esposta (2260)
- Verifica SSL abilitata di default

## Troubleshooting

### Container Non Si Avvia
1. Verifica variabili ambiente impostate
2. Controlla connettività database
3. Verifica disponibilità porta 2260

### Problemi Connessione Database
```bash
# Test da container
docker exec -it maotrade python -c "import pymysql; print('MySQL OK')"

# Controlla environment
docker exec -it maotrade env | grep DB_
```

### Problemi Performance
```bash
# Risorse container
docker stats maotrade

# Utilizzo memoria
docker exec -it maotrade free -h

# Lista processi
docker exec -it maotrade ps aux
```