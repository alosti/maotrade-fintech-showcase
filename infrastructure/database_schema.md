# Database Schema - MAOTrade

Architettura database del sistema MAOTrade con descrizione tabelle principali.

## Database Structure

Il sistema utilizza database MySQL e MongoDB:

### MySQL Databases

#### 1. `maohome` - Configurazione Sistema
Database principale per configurazione sistema, utenti, account e simboli.

#### 2. `maodata` - Dati Storici
Database per storage dati storici ticker e analisi.

#### 3. Database Trading Dinamici (`mt_{account}`)
Database creati dinamicamente per ogni account trading.
Gestiti in server MySQL separato in container nella stessa rete (`mt-network`) dei container MAOTrade.

### MongoDB Database

#### `maologs` - Log Aggregation
Database MongoDB per log centralizzati di tutti i componenti.
- **Collection**: `logs`
- **Gestito da**: Fluentd per aggregazione log
- **Network**: Fuori dalla rete Docker `mt-network` (installazione nativa per performance)

## Utenti Database

### MySQL Users
```sql
-- Utente principale applicazione
maotrade / [password_app]
- Permessi: maohome.* + mt_%.* (trading databases)

-- Utente gestione dati
maohome / [password_data] 
- Permessi: maohome.* + maodata.*

-- Utente monitoring
nagios / [password_monitoring]
- Permessi: information_schema.* (solo lettura)
```

### MongoDB Users
```javascript
// Utente gestione log
maologs / [password_logs]
- Permessi: lettura e scrittura database maologs
```

## Tabelle Principali MySQL

### Core System (`maohome`)

#### `mtrace_users`
Gestione utenti sistema
```sql
id, userid, displayname, email, valido, stato, admin
```

#### `accounts` 
Account trading per utenti
```sql
id, userid, accountid, accountdescr, accountdata, 
demoaccount, active, mt_host, mt_port, c_brokers
```
- `accountdata`: Dati account criptati
- `c_brokers`: FK a tabella brokers

#### `brokers`
Configurazione broker supportati
```sql
id, code, name, amclass, config
```
- `amclass`: Classe adapter per broker specifico
- `config`: Configurazione JSON per broker

#### `symbols`
Simboli trading disponibili
```sql
id, epicData, epic, name, enabled, idsession
```
- `epicData`: Identificativo interno simbolo
- `epic`: Codice simbolo per trading

#### `symbols_brokers`
Mapping simboli specifico per broker
```sql
id, idsymbol, epic, c_brokers
```

#### `symbols_tickers`
Mapping simboli a ticker esterni per recupero dati storici
```sql
id, epicData, tickerid, enabled
```

#### `mtpods`
Container trading gestiti
```sql
id, c_accounts, pod_id, name, descr, op_mode, 
op_request, state, exit_code, started_at, config
```
- `op_mode`: Modalità operativa (stopped, running)
- `state`: Stato container (stopped, error, running)

### Data Storage (`maodata`)

#### `hst_index`
Indice per dati storici
```sql
id, c_mtrace_tickers, startFrame, endFrame, enabled, tableName
```

#### `hst_template`
Template per tabelle dati storici
```sql
dateFrame, date, open, min, max, close, volume, count
```
- Ogni ticker ha tabella dinamica basata su questo template

#### `news`
Feed notizie di mercato
```sql
title, img, link, pubDate, type
```

### User Data (`maohome`)

#### `mtrace_users_tickers`
Ticker seguiti da utenti
```sql
id, c_users, c_tickers, enabled, mt_modified, mt_created
```

#### `mtrace_datastore`
Cache dati utente
```sql
id, c_users, c_tickers, data, store, mt_modified
```
- `store`: JSON con dati analisi/cache per ticker

#### `mtrace_devices`
Device registrati per notifiche
```sql
id, c_users, deviceid, gcmregid, marca, modello, 
flgpush, flggcmpush
```

## MongoDB Log Structure

### Collection `logs` (database `maologs`)

#### Esempio Log MAOTrade
```json
{
  "_id": ObjectId("67ed006ded1c460010459ceb"),
  "fileLog": "[2025-04-02 09:16:29,283] [ERROR   ] [Config] Parametri system FUTC non corretti",
  "localtime": "2025-04-02 09:16:29,283",
  "module": "ConfigHelper",
  "funcName": "read_config",
  "lineno": 404,
  "levelName": "ERROR",
  "thread": "MainThread",
  "compname": "Config",
  "stacktrace": null,
  "app": "maotrade",
  "mtaccount": "aosti_ig_demo1",
  "topic": 0,
  "topicId": "",
  "message": "Parametri system FUTC non corretti",
  "timestamp": ISODate("2025-04-02T09:16:29.283Z")
}
```

#### Esempio Log MAOPod
```json
{
  "_id": ObjectId("67ed006ded1c460010459cea"),
  "fileLog": "[2025-04-02 11:16:28,723] [INFO    ] [PodManager] Avvio pod mt_aosti_ig_demo1...",
  "localtime": "2025-04-02 11:16:28,723",
  "module": "PodManager",
  "funcName": "start_container",
  "lineno": 318,
  "levelName": "INFO",
  "thread": "MainThread",
  "compname": "PodManager",
  "stacktrace": null,
  "app": "maotrade",
  "mtaccount": "aosti_ig_demo1",
  "message": "Avvio pod mt_aosti_ig_demo1: {'image': 'maotrade', 'name': 'mt_aosti_ig_demo1'...}",
  "topic": null,
  "topicId": null,
  "timestamp": ISODate("2025-04-02T09:16:28.723Z")
}
```

#### Campi Log Comuni
- **app**: Componente che genera il log (maotrade, maopod, etc.)
- **mtaccount**: Account trading collegato all'operazione
- **compname**: Nome componente interno
- **module/funcName/lineno**: Informazioni debug codice
- **levelName**: Livello log (DEBUG, INFO, WARNING, ERROR)
- **timestamp**: Timestamp UTC operazione
- **topic/topicId**: Categorizzazione log per filtraggio

## Stored Procedures

### `encrypt_account_data(acc_data, pass)`
Crittografia dati account sensibili
```sql
SELECT CAST(TO_BASE64(aes_encrypt(acc_data, pass)) as CHAR(2048))
```

### `epic_from_tickerid(tickerid, brokerid)`
Risoluzione ticker -> epic per broker specifico
```sql
-- Restituisce mapping ticker a epic per trading
```

## Database Dinamici Trading

### Pattern `mt_{account_id}`
Ogni account trading ha database dedicato:
- Tabella segnali
- Storico operazioni  
- Log attività trading system
- Salvataggio state system

### Architettura Network
- **MySQL Trading Databases**: Container separato nella rete `mt-network`
- **MySQL Sistema**: Server principale per maohome/maodata
- **MongoDB + Fluentd**: Installazione nativa (fuori Docker per performance)

### Permessi
```sql
-- maotrade user ha accesso a tutti mt_% databases
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, 
      LOCK TABLES, EXECUTE, SHOW VIEW ON `mt_%`.* 
TO `maotrade`@`localhost`;
```

## Log Aggregation Architecture

### Flusso Log
1. **Componenti MAOTrade** → Log strutturati
2. **Fluentd** → Aggregazione e parsing log
3. **MongoDB** → Storage centralizzato in collection `logs`

### Metadati Specifici
Ogni componente inserisce metadati per tracking:
- **mtaccount**: Identifica account trading collegato
- **app**: Identifica componente sorgente
- **topic**: Categorizzazione operazione

## Considerazioni Architettura

### Separazione Dati
- **Configurazione**: `maohome` 
- **Dati Mercato**: `maodata`
- **Trading Live**: `mt_{account}` (server separato)
- **Log Centrali**: `maologs` (MongoDB)

### Sicurezza
- Dati account criptati con AES
- Utenti database con permessi limitati
- Password non in chiaro

### Performance
- Indici su chiavi di ricerca frequenti
- Vista per accesso ottimizzato ticker
- Cache dati utente in `mtrace_datastore`
- MongoDB e Fluentd nativi per performance I/O

### Monitoring
- Utente `nagios` per health check database
- Log operazioni tracciati in MongoDB
- Tracking stato container in `mtpods`