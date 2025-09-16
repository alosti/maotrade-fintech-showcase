# Error Handling Strategies in MAOTrade

Un sistema di trading deve gestire errori di ogni tipo: network failures, API broker down, database disconnections, dati corrotti. Ecco come li affronto in MAOTrade.

## Classificazione degli Errori

### Errori Recoverable vs Non-Recoverable

```python
# Dal mio codice reale - IGClient.py
def _process_response_error(self, response: dict):
    """Analizza la response e determina se l'errore è bloccante"""
    ig_error = response.get('json', {}).get('errorCode', "genericError")
    
    response['error'] = {
        'msg': f"ig.error: {ig_error}",
        'error': ig_error,
        'exception': None,
        'block': True if response['status_code'] == 401 else False,  # Auth errors = fatal
    }
```

**Recoverable**: Network timeout, broker API temporaneamente down, database connection loss  
**Non-Recoverable**: Authentication failed, invalid epic, system logic errors

### Error Code Enums

```python
# Dal BaseAccountManager.py - classificazione precisa degli errori
class MarketHistoryDataSrvCode(IntEnum):
    OK = 0,
    ERROR_CODE_BROKER = 1,            # Retry possibile
    ERROR_CODE_NETWORK = 2,           # Retry possibile
    ERROR_CODE_INVALID_EPIC = 3,      # Errore definitivo
    ERROR_CODE_INVALID_TIMEFRAME = 4, # Errore definitivo  
    ERROR_CODE_API_NOT_CONNECTED = 5, # Retry possibile
    ERROR_CODE_GENERAL = 6            # Valuta caso per caso
```

Ogni errore ha un codice specifico che determina la strategia di recovery.

## Strategia 1: Retry con Backoff

### Database Connection Recovery

```python
# Dal DBManager.py reale - retry automatico per query database
@contextmanager
def get_connection(self):
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            if not self.engine:
                self.connect()
            with self.engine.connect() as conn:
                yield conn
            break
        except DisconnectionError as e:
            retry_count += 1
            self.logger.warning(f"Connessione persa, tentativo {retry_count} di {max_retries}")
            if retry_count < max_retries:
                time.sleep(3)  # Backoff fisso di 3 secondi
                self.reconnect()
            else:
                raise SQLAlchemyError(f"Falliti i tentativi dopo {max_retries} tentativi")
```

**Quando uso retry:**
- Database connection loss → 3 tentativi con 3 sec di pausa
- Market data subscription fails → fino a 5 tentativi con backoff progressivo
- Summary sending fails → retry infinito con backoff esponenziale

### Market Data Subscription Retry

```python
# Dal TradeMgr.py reale - gestione errori sottoscrizione dati
elif request['errorCode'] == 2:  # Errore broker API
    if tt['retryRequestMktData'] > 5:
        # Dopo 5 tentativi, blocca il system
        tt['requestMktData'] = MktReqData.FAILED
        tt['system'].set_error_state()
        self._set_title_operate(signal, False, TitleOperateErrorCode.DATA_ERROR)
    else:
        # Programma nuovo tentativo con backoff
        tt['nextMktRequest'] = time_now + (tt['timeMktNextReq'] * tt['retryRequestMktData'])
        tt['retryRequestMktData'] += 1
```

**Pattern**: Exponential backoff limitato. Dopo 5 fallimenti, blocco il trading system per sicurezza.

## Strategia 2: Circuit Breaker Pattern

### System Error States

```python
# Dal BaseSystem.py reale - stato di errore che blocca operazioni
def set_error_state(self):
    if self._params['systemCompleted'] or self._params['systemError']:
        return
        
    self.consoleLog("System IN ERRORE", Severity.CRITICAL)
    self._params['systemError'] = True
    # System bloccato - non invia più ordini
```

**Trigger per error state:**
- Impossibile sottoscrivere dati di mercato dopo 5 tentativi
- Errore critico nella logica del trading system
- Broker account sospeso o disabilitato

### Broker Connection Circuit Breaker

```python
# Dal TradeMgr.py reale - gestione disconnessioni broker
def on_account_disconnected(self, code: int):
    if code == 1:
        # Disconnessione definitiva - troppi errori
        self._log.error("Interrotta connessione vs Broker causa troppi errori")
        self._notify.send_message("Connessione vs Broker interrotta",
                                "Causa errori, contattare assistenza",
                                Severity.CRITICAL)
    elif code == 2:
        # Disconnessione temporanea - tentativi di riconnessione
        self._log.error("Persa la connessione vs Broker") 
        if self.is_trade_session_open:
            self._notify.send_message("Connessione vs Broker persa",
                                    "Tentativi riconnessione in corso",
                                    Severity.CRITICAL)
```

**Logica**: Distinguo tra errori temporanei (retry) e definitivi (stop trading + alert).

## Strategia 3: Graceful Degradation

### Queue-Based Error Isolation

```python
# Dal GatewayInterface.py reale - retry automatico summary sending
class SummarySender(threading.Thread):
    def _call_send_summary(self, summary: dict) -> bool:
        try:
            self._service_helper.update_summary(summary['idAccount'], 
                                               summary['validUntil'], 
                                               summary['summary'])
            self._summary_retry = None
            self._num_retry = 0
            return True
        except (ServiceException, ServiceResultException):
            self._summary_retry = summary
            self._num_retry += 1
            if self._num_retry == 1 or self._num_retry % 20 == 0:
                self._log.exception(f"Errore invio summary, tentativi: {self._num_retry}")
        return False
```

**Strategia**: Se l'invio summary fallisce, continuo a operare ma loggo l'errore. Il summary non è critico per il trading.

### Epic Validation Fallback

```python
# Dal BaseAccountManager.py reale - gestione epic non trovati
for epic_data in epics:
    broker_epic = epic_data['epicBroker']
    if not broker_epic:
        self.log.error(f"Epic {epic_data['epic']} non trovato lato broker")
        response['errorCode'] = GenericSrvCode.ERORR.value
        response['state'] = False
        continue  # Continua con gli altri epic
```

**Pattern**: Un epic non valido non blocca l'elaborazione degli altri. Fail-fast per il singolo, continua per il resto.

## Strategia 4: Monitoring e Alerting

### Database Health Monitoring

```python
# Dal DBManager.py reale - monitoraggio continuo connessioni
def _monitor_connections(self):
    while not self._stop_monitoring:
        try:
            time.sleep(30)  # Check ogni 30 secondi
            if datetime.now() - self.last_connection_check > self.connection_check_interval:
                with self.get_connection() as conn:
                    conn.execute(text("SELECT 1"))
                self.last_connection_check = datetime.now()
                if not self.is_healthy:
                    self.logger.info("Connessione al database ripristinata")
                    self.is_healthy = True
        except Exception as e:
            if self.is_healthy:
                self.logger.error(f"Monitoraggio database: connessione persa - {str(e)}")
                self.is_healthy = False
```

**Scopo**: Detection proattiva di problemi prima che impattino il trading.

### Connection Pool Events

```python
# Dal DBManager.py reale - logging dettagliato connessioni
@event.listens_for(self.engine.pool, 'connect')
def receive_connect(conn, branch):
    self.logger.debug("Creata nuova connessione al database")

@event.listens_for(self.engine.pool, 'close_detached')  
def receive_disconnect(conn, branch):
    self.logger.debug("Connessione al database chiusa")
```

**Beneficio**: Visibilità completa su cosa succede al connection pool.

## Strategia 5: Safe Defaults

### Configuration Validation

```python
# Dal DBManager.py reale - parametri sicuri di default
def __init__(self, user: str, password: str, host: str, database: str,
             port: int = 3306,
             pool_size: int = 5,      # Conservativo
             pool_recycle: int = 3600, # Ricicla ogni ora
             pool_timeout: int = 30):  # Timeout ragionevole
```

### Error State Defaults

```python
# Quando qualcosa va male, assumo il case più sicuro
if not self.is_healthy:
    # Se DB è down, non fare trading
    return False
    
if connection_lost:
    # Se perdo connessione, non eseguire ordini
    self.set_blocked(True)
```

## Lessons Learned

### Cosa Funziona

1. **Retry limitato**: Mai retry infinito su operazioni critiche
2. **Error codes specifici**: Ogni errore ha un codice e una strategia
3. **Circuit breaker**: Dopo N errori, blocco automatico  
4. **Monitoring proattivo**: Controllo stato ogni 30 secondi
5. **Safe defaults**: In dubbio, non fare nulla

### Errori Evitati

1. ❌ **Silent failures**: Ogni errore viene loggato con severity appropriata
2. ❌ **Resource leaks**: Context manager per database connections
3. ❌ **Infinite retry**: Sempre un limite massimo di tentativi
4. ❌ **Blocking errors**: Threading per operazioni che possono fallire
5. ❌ **Data corruption**: Transazioni database atomiche

Il sistema è in funzione da anni, con intervento manuale limitato alla sola manutenzione programmata.
