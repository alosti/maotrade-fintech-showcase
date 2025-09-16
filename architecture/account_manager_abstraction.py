"""
MAOTrade - Account Manager Pattern

Estratto dal sistema reale che mostra come ho implementato l'astrazione 
multi-broker. Ogni broker implementa questa interfaccia, permettendo a 
MAOTrade di operare su qualsiasi broker senza modifiche al core.

Questo NON è codice eseguibile, ma una vetrina dell'architettura implementata.
"""

from abc import ABC, abstractmethod
from queue import Queue
from typing import Dict, Any
from enum import IntEnum


class AccountStatus(IntEnum):
    """Stati account broker - dal mio sistema reale"""
    ENABLED = 0
    DISABLED = 1
    SUSPENDED_FROM_DEALING = 2
    UNDEFINED = 99


class TradingTime(IntEnum):
    """Stati sessione trading - dal mio sistema reale"""
    CLOSE = 0
    OPEN = 1
    TO_OPEN = 2
    TO_CLOSE = 3


class BaseAccountManager(ABC):
    """
    Classe base astratta per tutti gli Account Manager.
    
    Ogni broker (IG Trading, Interactive Brokers, etc.) implementa
    questa interfaccia. Il core MAOTrade opera sempre con le stesse API
    indipendentemente dal broker sottostante.
    
    Pattern implementato nel mio sistema reale in produzione.
    """
    
    def __init__(self, config: Dict[str, Any], in_queue: Queue, out_queue: Queue):
        """
        Setup base per ogni Account Manager
        
        Args:
            config: Configurazione specifica del broker
            in_queue: Coda richieste da MAOTrade
            out_queue: Coda risposte verso MAOTrade
        """
        self._config = config
        self._in_queue = in_queue
        self._out_queue = out_queue
        self._server_running = False
        self._log = None  # Logger specifico per questo account manager
        
        # Stato gestito da ogni implementazione
        self._state = {
            'tradingTime': TradingTime.CLOSE,
            'account': {
                'valid': False,
                'requestInfo': False,
                'nextRequestInfo': 0
            },
            'portfolio': {
                'valid': False,
                'requestInfo': False,
                'nextRequestInfo': 0
            }
        }

    # === METODI CHE OGNI BROKER DEVE IMPLEMENTARE ===

    @abstractmethod
    def account_manager_main(self, time_now: int):
        """
        Main loop chiamato ad ogni iterazione.
        
        Qui ogni broker gestisce:
        - Connessioni ad API specifiche
        - Processing messaggi asincroni
        - Health check sulle connessioni
        - Retry logic specifica del broker
        
        Args:
            time_now: Unix timestamp corrente
        """
        pass

    @abstractmethod
    def do_async_request_account_info(self):
        """
        Richiede informazioni account al broker.
        
        Ogni broker implementa la sua logica:
        - IG: REST API call
        - IB: TWS message 
        - FIX: AccountDataRequest
        """
        pass

    @abstractmethod
    def do_async_request_portfolio(self):
        """
        Richiede posizioni aperte al broker.
        
        Deve popolare self._portfolio_info con le posizioni correnti.
        """
        pass

    @abstractmethod
    def do_async_request_order_open(self, order: 'BaseOrder'):
        """
        Esegue apertura posizione.
        
        Args:
            order: Oggetto ordine con tutti i parametri necessari
        """
        pass

    @abstractmethod
    def do_async_request_order_close(self, order: 'BaseOrder'):
        """
        Esegue chiusura posizione.
        
        Args:
            order: Oggetto ordine per chiusura
        """
        pass

    @abstractmethod
    def do_async_request_market_data(self, request: dict) -> bool:
        """
        Gestisce sottoscrizioni dati real-time.
        
        Args:
            request: {
                'subscribe': bool,
                'epic': str,
                'epicBroker': str, 
                'timeFrame': int
            }
            
        Returns:
            True se sottoscrizione OK, False altrimenti
        """
        pass

    # === LIFECYCLE METHODS ===

    @abstractmethod
    def on_account_manager_init(self):
        """
        Inizializzazione Account Manager.
        
        Returns:
            Tuple con:
            - success: bool
            - account_info: BaseAccountInfo (classe specifica per la gestione account)
            - portfolio_info: BasePortfolioInfo (classe specifica per la gestione portfolio)  
            - order_template: BaseOrder
            - history_frames: dict timeframes storici
            - data_frames: dict timeframes real-time
        """
        pass

    @abstractmethod
    def on_account_manager_terminate(self):
        """Cleanup alla terminazione"""
        pass

    @abstractmethod
    def on_trading_open(self, time_now: int):
        """Chiamata quando si apre una sessione di trading"""
        pass

    @abstractmethod
    def on_trading_close(self, time_now: int):
        """Chiamata quando si chiude una sessione di trading"""
        pass

    # === UTILITY METHODS (già implementati nel sistema base) ===

    def _send_message(self, service_id: int, data: dict = None, service_code: int = 0):
        """
        Invia messaggio al core MAOTrade.
        
        Ogni Account Manager usa questo per comunicare stati,
        dati di mercato, risultati ordini al TradeMgr.
        """
        message = {
            'service': service_id,
            'srvCode': service_code,
            'data': data or {}
        }
        self._out_queue.put(message)

    def response_async_account_info(self, error: str = ""):
        """
        Callback per risposta info account.
        
        Da chiamare dopo aver ricevuto i dati dell'account dal broker.
        """
        if error:
            self._log.error(f"Richiesta account fallita: {error}")
            self._state['account']['valid'] = False
        else:
            self._log.debug("Richiesta info account OK")
            self._state['account']['requestInfo'] = False

    def response_async_portfolio(self, error: str = ""):
        """
        Callback per risposta portfolio.
        
        Da chiamare dopo aver ricevuto le posizioni dal broker.
        """
        if error:
            self._log.error(f"Richiesta portfolio fallita: {error}")
            self._state['portfolio']['valid'] = False
        else:
            self._log.debug("Richiesta portfolio OK")
            self._state['portfolio']['requestInfo'] = False


class BaseAccountInfo:
    """
    Informazioni account standardizzate.
    
    Ogni broker popola questa struttura con i suoi dati specifici,
    ma MAOTrade vede sempre la stessa interfaccia.
    """
    
    def __init__(self):
        self.api_conn = False           # Connessione API
        self.feed_conn = False          # Connessione feed dati
        self.accountNameId = ""         # ID account
        self.accountName = ""           # Nome account
        self.status = AccountStatus.UNDEFINED
        self.pnl = 0.0                  # P&L totale
        self.usedMargin = 0.0           # Margine utilizzato
        self.totalCash = 0.0            # Cash disponibile
        self.currency = "EUR"           # Valuta base
        self.lastUpdate = 0             # Timestamp ultimo aggiornamento
        self.updated = False            # Flag aggiornamento

    def to_dict(self, trading_session: TradingTime) -> dict:
        """
        Converte in dizionario standard per MAOTrade.
        
        Returns:
            Dizionario con formato standard che TradeMgr si aspetta
        """
        self.updated = False
        return {
            'connected': self.api_conn,
            'feedAvailable': self.feed_conn,
            'tradingSessionOpen': trading_session == TradingTime.OPEN,
            'accountNameId': self.accountNameId,
            'accountName': self.accountName,
            'status': self.status.value,
            'pnl': self.pnl,
            'usedMargin': self.usedMargin,
            'totalCash': self.totalCash,
            'currency': self.currency,
            'lastUpdate': self.lastUpdate
        }


class BaseOrder:
    """
    Rappresentazione ordine standardizzata.
    
    Ogni broker riceve ordini in questo formato e li converte
    nella sua rappresentazione specifica.
    """
    
    def __init__(self):
        self.epic = ""              # Epic MAOTrade
        self.epicBroker = ""        # Epic specifico broker
        self.qty = 0.0              # Quantità
        self.stopPrice = 0.0        # Stop loss
        self.orderType = 0          # Market/Limit/Stop
        self.action = 0             # Open/Close/Modify
        self.dealStatus = 0         # Stato processing
        self.errorMessage = ""      # Messaggio errore
        
    def validate_order(self) -> bool:
        """Validazione base ordine"""
        return self.epic != "" and self.qty > 0


# === ESEMPIO IMPLEMENTAZIONE BROKER SPECIFICO ===

class IGAccountManagerExample(BaseAccountManager):
    """
    Esempio di implementazione per IG Trading.
    
    Questa è una versione semplificata che mostra il pattern.
    L'implementazione completa gestisce:
    - IGClient per REST API
    - LightStreamer per real-time
    - Retry logic e error handling
    """
    
    def __init__(self, config: dict, in_queue: Queue, out_queue: Queue):
        super().__init__(config, in_queue, out_queue)
        # Nel sistema reale:
        # self._client = IGClient(config)
        # self._lsclient = None
        pass
    
    def account_manager_main(self, time_now: int):
        """
        Main loop specifico per IG Trading.
        
        Gestisce connessioni API REST e LightStreamer.
        """
        # Nel sistema reale gestisco:
        # 1. Connessione API REST se disconnesso
        # 2. Connessione LightStreamer per feed
        # 3. Processing messaggi asincroni
        # 4. Health check e retry logic
        pass
    
    def do_async_request_order_open(self, order: BaseOrder):
        """
        Implementazione IG-specifica per apertura ordini.
        
        Nel sistema reale:
        1. Richiedo market details per l'epic
        2. Creo OTC position request 
        3. Invio al broker via REST API
        4. Gestisco response asincrona
        """
        # Esempio del pattern che uso:
        # self._client.request_market_details(
        #     epic=order.epicBroker,
        #     response_callback=self._handle_order_response,
        #     response_data={'order': order}
        # )
        pass
    
    def do_async_request_portfolio(self):
        """IG-specific portfolio request"""
        # Nel reale: self._client.request_positions(response_callback=self._handle_positions)
        pass
    
    def do_async_request_account_info(self):
        """IG-specific account info request"""  
        # Nel reale: self._client.request_account_info(response_callback=self._handle_account)
        pass
    
    def do_async_request_market_data(self, request: dict) -> bool:
        """IG-specific market data subscription"""
        if request['subscribe']:
            # Nel reale: self._lsclient.subscribe_price_data(...)
            return True
        else:
            # Nel reale: self._lsclient.unsubscribe_price_data(...)
            return True
    
    def on_account_manager_init(self):
        """
        Setup timeframes supportati da IG.
        
        Returns:
            Configurazione specifica IG con mapping timeframes
        """
        # Mapping timeframes IG -> MAOTrade (dal mio sistema reale)
        history_frames = {1: "MINUTE", 5: "MINUTE_5", 60: "HOUR", -1: "DAY"}
        data_frames = {300: "5MINUTE", 60: "1MINUTE", 1: "SECOND"}
        
        return True, BaseAccountInfo(), None, BaseOrder(), history_frames, data_frames
    
    def on_account_manager_terminate(self):
        """Cleanup IG connections"""
        # Nel reale: self._client.terminate(), self._disconnect_feed()
        pass
    
    def on_trading_open(self, time_now: int):
        """IG-specific trading open logic"""
        # Nel reale: rinnovo token API, reset connessioni
        pass
    
    def on_trading_close(self, time_now: int):  
        """IG-specific trading close logic"""
        # Nel reale: disconnect feed, cleanup
        pass


"""
VANTAGGI DI QUESTO PATTERN:

1. ASTRAZIONE COMPLETA: MAOTrade non sa che broker sta usando
2. ESTENSIBILITÀ: Nuovo broker = implementa BaseAccountManager
3. MANUTENIBILITÀ: Bug su broker specifico = fix isolato
4. TESTABILITÀ: Mock broker per testing
5. CONFIGURABILITÀ: Broker selezionato da configurazione runtime

SFIDE RISOLTE:

- API diverse: REST vs WebSocket vs FIX vs TCP
- Formati dati diversi: JSON vs XML vs binary
- Autenticazione diversa: API keys vs certificates vs tokens  
- Timeframes diversi: mapping automatico
- Error handling diverso: retry logic broker-specific

Il risultato: sistema che supporta qualsiasi broker senza modifiche al core.
"""