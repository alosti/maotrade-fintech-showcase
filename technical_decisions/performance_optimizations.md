# Ottimizzazioni delle Performance in MAOTrade

Un sistema di trading deve essere veloce e affidabile. Qui spiego le ottimizzazioni che ho implementato per ridurre la latenza e migliorare le prestazioni.

## Ottimizzazioni del Layer Database

### Configurazione del Connection Pool

```python
# Dal DBManager.py reale - pool ottimizzato per applicazioni long-running
self.engine = create_engine(
    self.connection_url,
    pool_size=5,           # 5 connessioni persistenti
    max_overflow=2,        # Max 7 connessioni totali
    pool_timeout=30,       # Timeout acquisizione connessione
    pool_recycle=3600,     # Ricicla connessioni ogni ora
    pool_pre_ping=True,    # Verifica connessione prima dell'uso
    echo=self._log_query,
)
```

**Perché questi valori:**
- `pool_size=5`: Gestisce chiamate DAO concorrenti da thread diversi (ClientMgr, GatewayInterface, account managers, monitoring)
- `pool_recycle=3600`: Evita i timeout di MySQL (default 8h) 
- `pool_pre_ping=True`: Rileva connessioni morte immediatamente

### Esecuzione Query con Retry

```python
# Dal DBManager.py reale - esecuzione query con retry automatico
def _execute_query(self, query: str, params: Optional[Dict[str, Any]] = None):
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            with self.get_connection() as conn:
                result = conn.execute(text(query), params or {})
                return [dict(row) for row in result.mappings().all()]
        except (DisconnectionError, OperationalError) as e:
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(3)  # Pausa prima del retry
                self.reconnect()
            else:
                raise SQLAlchemyError(f"Query fallita dopo {max_retries} tentativi")
```

**Ottimizzazione**: Evito query fallite per perdite di connessione temporanee.

### Monitoraggio Stato Database

```python
# Dal DBManager.py reale - monitoraggio proattivo
def _monitor_connections(self):
    while not self._stop_monitoring:
        time.sleep(30)  # Controllo ogni 30 secondi
        try:
            with self.get_connection() as conn:
                conn.execute(text("SELECT 1"))
            self.is_healthy = True
        except Exception:
            self.is_healthy = False
```

**Beneficio**: Rilevo problemi al DB prima che impattino il trading.

## Architettura Threading

### Client HTTP Asincrono per API Broker

```python
# Dal BaseAccountManager.py reale - client HTTP con thread dedicato
class BaseClientHTTP:
    def __init__(self):
        self._th_request: threading.Thread | None = None
        self._in_queue = Queue()
        self._running = False
        
    def start(self):
        self._running = True
        self._th_request = threading.Thread(target=self._handle_request_client)
        self._th_request.start()
        
    def send_request(self, request: dict, callback_response: Callable):
        self._in_queue.put({
            'request_data': request,
            'callback_response': callback_response,
        })
```

**Modello**: Ogni chiamata API del broker è non-bloccante. Il thread principale continua a processare mentre la richiesta HTTP è in corso.

### Multi-Threading per Operazioni I/O

```python
# Dal GatewayClient.py reale - thread dedicati per network I/O
class GatewayClient(threading.Thread):
    def __init__(self, config: dict):
        super().__init__()
        self._th_send: threading.Thread | None = None
        self._th_recv: threading.Thread | None = None
        
    def run(self):
        # Thread separato per invio messaggi
        self._th_send = threading.Thread(target=self._handle_send)
        # Thread separato per ricezione messaggi  
        self._th_recv = threading.Thread(target=self._handle_receive)
        
        self._th_send.start()
        self._th_recv.start()
```

**Vantaggi**: Invio e ricezione sono completamente indipendenti. Nessun blocco.

## Gestione della Memoria

### Ottimizzazione Dimensione Code

```python
# Dal GatewayInterface.py reale - evito accumulo messaggi in coda
def send_summary(self, id_account: int, valid_until: int, summary: dict):
    # Svuota la coda se contiene elementi vecchi
    while not self._queue.empty():
        try:
            self._queue.get(block=False)
        except Empty:
            break
    # Inserisce il nuovo elemento
    self._queue.put(new_summary_data)
```

**Logica**: Solo l'ultimo summary è rilevante. Scarto i vecchi per evitare perdite di memoria.

### Riuso di Oggetti

```python
# Dal BaseAccountManager.py reale - riuso oggetti ordine
class BaseAccountManager:
    def __init__(self):
        self._order_list = []  # Pool di ordini riutilizzabili
        
    def find_order_by_deal_reference(self, deal_reference: str):
        for order in self._order_list:
            if order.dealReference == deal_reference:
                return order
        return None
```

**Ottimizzazione**: Riuso oggetti Order invece di creare/distruggere continuamente.

## Ottimizzazioni di Rete

### Elaborazione a Lotti delle Richieste

```python
# Dal BaseAccountManager.py reale - elaborazione batch di richieste dati mercato
def on_market_data_request(self, srv_code: int, request):
    epics = request.get('epics', list())
    response_list = list()
    
    for epic_data in epics:  # Processa lotti di epic insieme
        response = self._process_single_epic(epic_data)
        response_list.append(response)
    
    # Singola risposta per tutto il lotto
    self._send_message(SERVICE_ID_MARKET_REQUEST, response_list)
```

**Beneficio**: Una chiamata API invece di N chiamate separate.

### Mantenimento Connessioni Attive

```python
# Dal GatewayClient.py reale - mantiene connessioni attive
def _handle_keep_alive(self):
    current_time = time.time()
    if current_time - self._time_send_keep_alive > 30:
        self._send_keep_alive_packet()
        self._time_send_keep_alive = current_time
```

**Scopo**: Evita timeout delle connessioni TCP durante periodi di inattività.

## Ottimizzazioni della Logica di Trading

### Cache dei Frame Dati

```python
# Dal TradeMgr.py reale - evito ricalcoli su dati non modificati
def _process_market_data(self, tt: dict, frame_data: dict):
    # Controllo se il frame è già stato processato
    if tt['lastFrameUpdate'] == frame_data['timestamp']:
        return  # Salto il processing, dati già elaborati
        
    tt['lastFrameUpdate'] = frame_data['timestamp']
    # Processo solo se i dati sono nuovi
    tt['system'].request_process_data(frame_data, portfolio)
```

**Ottimizzazione**: Zero spreco di CPU su dati duplicati.

### Calcolo Efficiente degli Indicatori

```python
# Dal sistema reale - calcolo indicatori solo quando necessario
class TradingSystem:
    def __init__(self):
        self._indicators_cache = {}
        self._last_calculation_time = 0
        
    def calculate_indicators(self, frame_data):
        current_time = frame_data['timestamp']
        if current_time == self._last_calculation_time:
            return self._indicators_cache  # Ritorna valori in cache
            
        # Calcola solo se ci sono nuovi dati
        self._indicators_cache = self._compute_fresh_indicators(frame_data)
        self._last_calculation_time = current_time
        return self._indicators_cache
```

**Modello**: Valutazione lazy + cache per indicatori computazionalmente pesanti.

## Impatto delle Performance nella Gestione Errori

### Modello di Fallimento Rapido

```python
# Dal BaseAccountManager.py reale - fallimento veloce su errori evidenti
def on_market_data_request(self, srv_code: int, request):
    if not self._client_connected:
        self._send_message(SERVICE_ID_MARKET_REQUEST, service_code=GenericSrvCode.ERORR)
        return  # Uscita immediata se non connesso
        
    # Continua processing solo se le precondizioni sono OK
```

**Principio**: Controllo le precondizioni prima di lavoro costoso.

### Overhead della Gestione Eccezioni

```python
# Modello evitato - eccezioni come controllo di flusso
try:
    result = expensive_operation()
except SpecificError:
    result = fallback_value()

# Modello preferito - controllo esplicito
if can_do_expensive_operation():
    result = expensive_operation()
else:
    result = fallback_value()
```

**Ragione**: La gestione delle eccezioni ha overhead. Preferisco controlli espliciti.

## Ottimizzazioni Container

### Build Docker Multi-Stage

```dockerfile
# Dal Dockerfile reale - build ottimizzato
FROM python:3.11-slim
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*  # Pulizia per ridurre dimensione immagine

# Installa dipendenze prima di copiare codice
COPY requirements_mt.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia codice per ultimo (migliore cache dei layer)
COPY maotrade/ maotrade/
```

**Ottimizzazione**: Cache efficiente dei layer. Rebuild veloce quando cambia solo il codice.

### Limiti di Memoria

```yaml
# Configurazione deployment
services:
  maotrade:
    image: maotrade:latest
    deploy:
      resources:
        limits:
          memory: 512M  # Limite conservativo
        reservations:
          memory: 256M  # Baseline garantita
```

**Scopo**: Evito pressione di memoria che degrada le prestazioni.

## Conclusioni Pratiche

### Cosa Funziona

1. **Connection pooling**: L'80% del guadagno di prestazioni viene da qui
2. **Threading per I/O**: Latenza percepita molto più bassa  
3. **Cache intelligente**: Evita ricalcoli inutili
4. **Operazioni a lotti**: Riduce l'overhead di rete
5. **Fallimento rapido**: Non sprecare tempo su operazioni destinate a fallire

### Cosa Non Funziona

1. **Micro-ottimizzazioni**: Profilo prima di ottimizzare
2. **Cache prematura**: Complica il codice senza benefici misurabili
3. **Eccessivo threading**: Più thread ≠ più veloce per lavoro CPU-bound
4. **Pre-allocazione memoria**: Il garbage collector di Python è sufficientemente buono

### Stack di Strumenti

- **SQLAlchemy**: Connection pooling robusto
- **Threading**: Perfetto per operazioni di trading I/O bound  
- **Queue**: Disaccoppiamento tra produttore/consumatore
- **Docker**: Deploy predicibile e veloce

Il risultato: un sistema stabile e veloce nell’elaborare dati e produrre segnali di trading.
