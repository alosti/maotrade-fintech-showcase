"""
MAOTrade - Framework BaseSystem per Trading Systems

Estratto dal sistema reale che mostra come ho implementato il framework
per sviluppare strategie di trading. Ogni sistema eredita da BaseSystem
e implementa solo la logica specifica, tutto il resto è gestito automaticamente.

Questo NON è codice eseguibile, ma una vetrina del framework implementato.
"""

from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Dict, Any, Tuple, List


class SystemAction(IntEnum):
    """
    Azioni possibili di un trading system.
    Enum dal mio sistema reale - ogni valore ha un significato preciso.
    """
    NOACTION = 0        # Nessuna azione
    ACTION_DELAY = 1    # Ritarda azione
    ACTION_PREBUY = 2   # Pre-acquisto  
    ACTION_BUY = 3      # Acquista
    ACTION_PRESELL = 4  # Pre-vendita
    ACTION_SELL = 5     # Vendi
    ACTION_BUYLOST = 6  # Acquisto perso
    ACTION_SELLLOST = 7 # Vendita persa
    ACTION_BUYSELL = 8  # Acquisto e vendita
    ACTION_HOLD = 9     # Mantieni posizione
    ACTION_FLAT = 10    # Chiudi posizione
    ACTION_STPR = 11    # Stop richiesto


class OrderExecState(IntEnum):
    """Stati esecuzione ordini - dal mio sistema reale"""
    JUST_CREATED = 0    # Appena creato
    SUBMITTED = 1       # Inviato al broker
    ACCEPTED = 2        # Accettato dal broker
    FILLED = 3          # Eseguito
    ERROR = 4           # Errore
    CANCELLED = 5       # Cancellato


class OrderOpType(IntEnum):
    """Tipo operazione ordine - dal mio sistema reale"""
    NO_OP = 0   # Nessuna operazione
    BUY = 1     # Acquisto
    SELL = 2    # Vendita


class OrderAuthorType(IntEnum):
    """Tipologia autore ordine - dal mio sistema reale"""
    AUTHOR_SYSTEM = 0     # Ordine automatico del sistema
    AUTHOR_RESTART = 1    # Ordine da ripresa sistema
    AUTHOR_USER = 2       # Ordine manuale utente
    AUTHOR_UNDEFINED = 99 # Non definito


class Severity(IntEnum):
    """Livelli di severità logging - dal mio sistema"""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class BaseSystem(ABC):
    """
    Classe base astratta per tutti i trading systems.
    
    Fornisce automaticamente:
    - State management con persistenza
    - Gestione ordini e tracking
    - Logging strutturato
    - Recovery dopo crash
    - Validazione parametri
    - Ciclo di vita completo
    
    Ogni sistema implementa solo la logica specifica.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Setup base per ogni trading system.
        Nel sistema reale viene chiamato _do_init() invece di __init__.
        """
        # Stato del sistema - tutto quello che metto qui viene salvato automaticamente
        self._state = {}
        self._state_updated = False
        
        # Parametri di configurazione
        self._params = {}
        self._system_params = {}
        
        # Configurazione sistema
        self._config = config
        self.epic = config.get('epic', '')
        self.time_frame = config.get('timeFrame', 0)
        
        # Controllo esecuzione
        self.blocked = False
        self.system_action = SystemAction.NOACTION
        self.system_signal = ""
        
        # Gestione ordini
        self._order_requests = []
        # Se l'ordine non viene inviato al broker entro 2 minuti viene annullato l'invio
        self.max_order_submit_time_in_secs = 120
        # Intervallo di attesa tra un tentativo ed il successivo per invio ordine a broker
        self.order_submit_time_delay_in_secs = 30
        
        # Logging
        self._log = None  # Logger del sistema
        
    # === METODI CHE OGNI SISTEMA DEVE IMPLEMENTARE ===
    
    @abstractmethod
    def do_validate_signal(self, signal: dict, system_params: dict, 
                          portfolio: dict, import_uid: str = "") -> bool:
        """
        Valida il segnale secondo le regole del sistema.
        
        Chiamata PRIMA dell'attivazione per verificare che tutti i parametri
        siano corretti e le condizioni di mercato appropriate.
        
        Args:
            signal: Segnale da validare con epic, parametri, etc.
            system_params: Parametri configurazione sistema dall'utente
            portfolio: Portfolio corrente con posizioni aperte
            import_uid: ID per logging tracciabile
            
        Returns:
            True se validazione OK, False altrimenti
            
        Esempio implementazione:
            # Controllo parametri obbligatori
            if not self.check_system_param(system_params, 'signal'):
                return False
            if not self.check_system_param(system_params, 'qty'):
                return False
            return True
        """
        pass
    
    @abstractmethod  
    def do_initialize_system(self, portfolio: dict, import_uid: str, 
                           is_first_init: bool) -> bool:
        """
        Inizializza il sistema con le condizioni di mercato attuali.
        
        Chiamata dopo la validazione per setup del sistema.
        Può essere chiamata anche per reinizializzazione dopo modifica parametri.
        
        Args:
            portfolio: Portfolio corrente
            import_uid: ID per logging
            is_first_init: True se prima inizializzazione, False se reinizializzazione
            
        Returns:
            True se inizializzazione OK, False altrimenti
            
        Esempio implementazione:
            # Estraggo parametri utente
            self._signal_type = self.get_system_param(self._system_params, 'signal')
            self._quantity = self.get_system_param(self._system_params, 'qty')
            
            # Inizializzo stato
            self._state['current_position'] = portfolio.get(self.epic, {}).get('qty', 0)
            self._state['system_ready'] = True
            
            return True
        """
        pass
    
    @abstractmethod
    def do_process_data(self, frame_data: dict, portfolio: dict) -> Tuple[SystemAction, float, float]:
        """
        CUORE DEL SISTEMA: elabora i dati di mercato e decide cosa fare.
        
        Chiamata ad ogni frame di dati ricevuto dal broker.
        Qui va tutta la logica specifica del trading system.
        
        Args:
            frame_data: Dati del frame corrente con:
                - frame: Unix timestamp del timeframe
                - open: Prezzo apertura
                - high: Prezzo massimo  
                - low: Prezzo minimo
                - close: Prezzo chiusura
                - vol: Volume
                - timeFrameEnd: True se candela completata
                - orderSubmitting: True se ordine in corso
                - timeNow: Timestamp corrente
            portfolio: Portfolio con posizioni correnti
            
        Returns:
            Tupla (SystemAction, quantità, prezzo_stop)
            
        Esempio implementazione:
            # Opera solo su candele complete
            if not frame_data['timeFrameEnd']:
                return SystemAction.NOACTION, 0, 0
                
            # La mia logica di trading
            if self._should_buy(frame_data, portfolio):
                return SystemAction.ACTION_BUY, 100, frame_data['close'] * 0.98
            elif self._should_sell(frame_data, portfolio):
                return SystemAction.ACTION_SELL, 100, frame_data['close'] * 1.02
            else:
                return SystemAction.NOACTION, 0, 0
        """
        pass
    
    @abstractmethod
    def do_resume_system(self, frame_data: List[dict], portfolio: dict, 
                        chart: Any, state: dict, log: list, 
                        time_now: int, import_uid: str) -> bool:
        """
        Ripristina il sistema dopo un crash o restart.
        
        Il framework salva automaticamente lo stato, questa funzione
        deve ricostruire lo stato interno dai dati salvati.
        
        Args:
            frame_data: Lista frame processati nella giornata
            portfolio: Portfolio corrente
            chart: Dati grafico (se disponibili)
            state: Stato salvato prima del crash
            log: Log messaggi del sistema
            time_now: Timestamp corrente
            import_uid: ID per logging
            
        Returns:
            True se ripresa OK, False altrimenti
            
        Esempio implementazione:
            # Ripristino stato interno
            if state:
                self._state.update(state)
                
            # Ricalcolo indicatori da dati storici
            for frame in frame_data:
                self._update_indicators(frame)
                
            return True
        """
        pass

    # === UTILITY METHODS (già implementati nel framework) ===
    
    def process_data(self, frame_data: dict, portfolio: dict):
        """
        Wrapper che gestisce il ciclo completo di elaborazione.
        
        Questo metodo è già implementato nel framework reale e:
        1. Normalizza il timestamp del frame
        2. Chiama do_process_data() del sistema specifico
        3. Gestisce le azioni ritornate (BUY/SELL/FLAT)
        4. Controlla stati di errore/blocco
        5. Gestisce timeout azioni
        6. Salva stato se modificato
        """
        # Normalizzazione timestamp
        frame_data['frame'] -= frame_data['frame'] % self.time_frame
        position = portfolio.get(self._params['epic'], dict())
        time_now = frame_data['timeNow']

        # Chiamo la logica del sistema
        action, action_qty, action_stop = self.do_process_data(frame_data, portfolio)

        # Se il sistema è completato, non processo
        if self.is_completed():
            action = SystemAction.NOACTION

        # Se c'è un ordine in corso, aspetto
        if frame_data['orderSubmitting']:
            return

        # Controllo stati di blocco/errore
        if action != SystemAction.NOACTION and (self.blocked or self.is_error_state()):
            if self.blocked:
                self.consoleLog("Ordine saltato per system bloccato", Severity.WARNING)
            elif self.is_error_state():
                self.consoleLog("Ordine saltato per system in errore", Severity.WARNING)
            return

        # Memorizzo ultima azione
        if action != SystemAction.NOACTION:
            self.system_action = action
            self._params['actionTime'] = frame_data['timeNow']
            
        # Timeout azioni (10 minuti)
        elif (self.system_action != SystemAction.NOACTION and 
              (frame_data['timeNow'] - self._params['actionTime']) > 600):
            self.system_action = SystemAction.NOACTION
            self._params['actionTime'] = 0

        # Esecuzione azioni
        self._execute_action(action, action_qty, action_stop, position)

    def _execute_action(self, action: SystemAction, action_qty: float, 
                       action_stop: float, position: dict):
        """
        Esegue l'azione richiesta dal sistema.
        
        Dal mio codice reale - gestisce BUY, SELL, FLAT con logica specifica.
        """
        if action == SystemAction.ACTION_FLAT and position.get('qty', 0.0):
            # Chiusura posizione
            delta_pos = abs(position.get('qty', 0.0)) - action_qty
            adj_qty = max(0.0, delta_pos)
            if adj_qty:
                self.consoleLog(f"FLAT: Chiudo posizioni: {adj_qty}", Severity.INFO)
                self.close_position(adj_qty)
            else:
                self.consoleLog("FLAT: Chiudo tutte le posizioni", Severity.INFO)
                self.close_position()
                
        elif action == SystemAction.ACTION_BUY:
            # Apertura posizione long
            if position.get('qty', 0.0) >= 0.0:
                self.consoleLog(f"BUY: Apro posizioni: {action_qty}", Severity.INFO)
                self.open_position(OrderOpType.BUY, action_qty, stop_price=action_stop)
            else:
                # Chiudo short e apro long
                self.consoleLog("BUY(1/2): Chiudo tutte le posizioni", Severity.INFO)
                self.close_position(on_filled_action=(action, action_qty, action_stop))
                
        elif action == SystemAction.ACTION_SELL:
            # Apertura posizione short
            if position.get('qty', 0.0) <= 0.0:
                self.consoleLog(f"SELL: Apro posizioni: {action_qty}", Severity.INFO)
                self.open_position(OrderOpType.SELL, action_qty, stop_price=action_stop)
            else:
                # Chiudo long e apro short
                self.consoleLog("SELL(1/2): Chiudo tutte le posizioni", Severity.INFO)
                self.close_position(on_filled_action=(action, action_qty, action_stop))

    def initialize_system(self, signal: dict, portfolio: dict, 
                         import_uid: str, is_first_init: bool) -> bool:
        """
        Inizializzazione completa del sistema.
        
        Wrapper che gestisce:
        - Setup parametri base
        - Estrazione parametri utente  
        - Chiamata do_initialize_system()
        - Logging risultati
        - Aggiornamento stati interni
        """
        if is_first_init:
            # Setup parametri di default
            self.max_order_submit_time_in_secs = 120
            self.frame_miss_updates_in_secs = self.time_frame * 3
            self._params['opId'] = signal.get('idOp', 0)
            self._params['dateOp'] = signal['dateOp']
            self._params['tradeStart'] = signal['startTrade']
            self._params['tradeEnd'] = signal['endTrade']

        # Stati del sistema
        self._params['systemCompleted'] = signal['completed']
        self.blocked = signal['blocked']
        self._params['systemError'] = not signal['operate']
        
        # Pulisco ordini pendenti
        self._order_requests.clear()
        
        # Estraggo parametri del sistema
        self._state['params'] = self._getsystem_params(signal['systemUserParams'])
        
        # Chiamo inizializzazione specifica
        ret_init = self.do_initialize_system(portfolio, import_uid, is_first_init)
        
        if ret_init:
            self.consoleLog("Inizializzazione system OK", Severity.INFO, import_uid)
            self.consoleLog(f"Segnale: {self.system_signal}", Severity.INFO, import_uid)
            self._state_updated = True
        else:
            self.consoleLog("Errore inizializzazione system", Severity.ERROR, import_uid)

        return ret_init

    # === UTILITY METHODS PER I SISTEMI ===
    
    def get_system_param(self, system_params: dict, key: str):
        """
        Estrae valore parametro sistema se presente e valorizzato.
        
        Dal mio codice reale - gestisce la struttura parametri MAOTrade.
        """
        return (system_params[key]['value'] 
                if system_params.get(key) and system_params[key].get('value') is not None 
                else None)

    def check_system_param(self, system_params: dict, key: str, 
                          error_msg_missing: str = "", 
                          error_msg_invalid: str = "", 
                          import_uid: str = "") -> bool:
        """
        Controlla presenza e validità parametro sistema.
        
        Args:
            system_params: Parametri sistema
            key: Chiave parametro da controllare
            error_msg_missing: Messaggio se parametro mancante
            error_msg_invalid: Messaggio se valore non valido
            import_uid: ID per logging
            
        Returns:
            True se parametro OK, False altrimenti
        """
        if not system_params.get(key):
            if error_msg_missing:
                self.consoleLog(error_msg_missing, Severity.ERROR, import_uid)
            return False
            
        value = system_params[key].get('value')
        if value is None:
            if error_msg_missing:
                self.consoleLog(error_msg_missing, Severity.ERROR, import_uid)
            return False
            
        # Ulteriori validazioni possono essere aggiunte qui
        return True

    def consoleLog(self, message: str, severity: Severity, import_uid: str = ""):
        """
        Logging strutturato per il sistema.
        
        Ogni messaggio viene taggato con:
        - Nome sistema
        - Severità  
        - Epic
        - Timestamp
        - Import UID per tracciabilità
        """
        if self._log:
            formatted_msg = f"[{self.epic}] {message}"
            if import_uid:
                formatted_msg = f"[{import_uid}] {formatted_msg}"
                
            if severity == Severity.DEBUG:
                self._log.debug(formatted_msg)
            elif severity == Severity.INFO:
                self._log.info(formatted_msg)
            elif severity == Severity.WARNING:
                self._log.warning(formatted_msg)
            elif severity == Severity.ERROR:
                self._log.error(formatted_msg)
            elif severity == Severity.CRITICAL:
                self._log.critical(formatted_msg)

    # === GESTIONE STATO E LIFECYCLE ===
    
    def is_completed(self) -> bool:
        """Controlla se sistema è in stato completato"""
        return self._params.get('systemCompleted', False)
    
    def set_completed(self):
        """Imposta sistema come completato"""
        self._params['systemCompleted'] = True
        self._state_updated = True
    
    def is_error_state(self) -> bool:
        """Controlla se sistema è in errore"""
        return self._params.get('systemError', False)
    
    def set_error_state(self):
        """Imposta sistema in errore"""
        self._params['systemError'] = True
        self._state_updated = True

    # === GESTIONE ORDINI ===
    
    def open_position(self, op_type: OrderOpType, qty: float, 
                     stop_price: float = 0.0, **kwargs):
        """
        Richiesta apertura posizione.
        
        Crea ordine e lo mette nella coda di elaborazione del Gateway.
        """
        order_request = self._create_order_request(
            op_type=op_type,
            qty=qty,
            stop_price=stop_price,
            **kwargs
        )
        self._order_requests.append(order_request)
        self.consoleLog(f"Richiesta apertura: {op_type.name} {qty} @ stop {stop_price}", 
                       Severity.INFO)

    def close_position(self, qty: float = 0, **kwargs):
        """
        Richiesta chiusura posizione.
        
        Se qty=0, chiude tutta la posizione.
        """
        order_request = self._create_order_request(
            op_type=OrderOpType.SELL,  # Sarà convertito in base alla posizione attuale
            qty=qty,
            is_close=True,
            **kwargs
        )
        self._order_requests.append(order_request)
        self.consoleLog(f"Richiesta chiusura: {qty if qty > 0 else 'tutto'}", 
                       Severity.INFO)

    def _create_order_request(self, **kwargs) -> dict:
        """
        Crea struttura richiesta ordine standard.
        
        Ritorna dizionario con tutti i campi necessari per il Gateway.
        """
        return {
            'epic': self.epic,
            'system': self.__class__.__name__,
            'timestamp': 0,  # Sarà popolato dal TradeMgr
            'author': OrderAuthorType.AUTHOR_SYSTEM,
            **kwargs
        }

    # === CALLBACK EVENTI (da sovrascrivere se necessario) ===
    
    def on_order_accepted(self, order: dict):
        """Chiamata quando ordine accettato dal broker"""
        self.consoleLog(f"Ordine accettato: {order.get('id', 'N/A')}", Severity.INFO)
    
    def on_order_filled(self, order: dict, time_now: int):
        """Chiamata quando ordine eseguito dal broker"""
        filled_qty = order.get('status', {}).get('filled', 0)
        avg_price = order.get('status', {}).get('avgFillPrice', 0)
        self.consoleLog(f"Ordine eseguito: {filled_qty} @ {avg_price}", Severity.INFO)
        
        # Nel sistema reale gestisco anche le azioni on_filled per ordini composti
        if order.get('authorType') == OrderAuthorType.AUTHOR_SYSTEM:
            action, qty, stop_price = order.get('onFilledAction', (SystemAction.NOACTION, 0, 0))
            if action != SystemAction.NOACTION:
                # Eseguo la seconda parte di un ordine composto (es. girata posizione)
                if action == SystemAction.ACTION_BUY:
                    self.consoleLog(f"BUY(2/2): Apro posizioni {qty}", Severity.INFO)
                    self.open_position(OrderOpType.BUY, qty, stop_price=stop_price)
                elif action == SystemAction.ACTION_SELL:
                    self.consoleLog(f"SELL(2/2): Apro posizioni {qty}", Severity.INFO)
                    self.open_position(OrderOpType.SELL, qty, stop_price=stop_price)
    
    def on_order_error(self, order: dict):
        """Chiamata quando errore su ordine"""
        error_msg = order.get('status', {}).get('errorMessage', 'Errore sconosciuto')
        self.consoleLog(f"Errore ordine: {error_msg}", Severity.ERROR)
        
        # Nel sistema reale: se errore su ordine automatico, metto sistema in errore
        if order.get('authorType') != OrderAuthorType.AUTHOR_USER:
            self.set_error_state()


# === ESEMPIO IMPLEMENTAZIONE SISTEMA CONCRETO ===

class FUTMExample(BaseSystem):
    """
    Esempio semplificato del sistema FUTM dal mio codice reale.
    
    FUTM gestisce segnali direzionali (BUY/SELL/FLAT) con quantità configurabili.
    Questo esempio mostra il pattern di implementazione.
    """
    
    def do_validate_signal(self, signal: dict, system_params: dict, 
                          portfolio: dict, import_uid: str = "") -> bool:
        """Validazione specifica FUTM"""
        # Controllo parametro signal obbligatorio
        if not self.check_system_param(system_params, 'signal',
                                     "Parametro signal non impostato", "", import_uid):
            return False
            
        # Controllo parametro quantity obbligatorio  
        if not self.check_system_param(system_params, 'qty',
                                     "Parametro qty non impostato", "", import_uid):
            return False
            
        # Validazione valore signal
        signal_value = self.get_system_param(system_params, 'signal')
        if signal_value not in ['BUY', 'SELL', 'FLAT', 'HOLD']:
            self.consoleLog(f"Signal non valido: {signal_value}", Severity.ERROR, import_uid)
            return False
            
        return True
    
    def do_initialize_system(self, portfolio: dict, import_uid: str, 
                           is_first_init: bool) -> bool:
        """Inizializzazione specifica FUTM"""
        trade_op = self._state['tradeOp'] = {}
        params = self._state['params']
        position = portfolio.get(self.epic, {}).get('qty', 0.0)
        
        # Determino azione sistema in base al signal
        signal_value = params['signal']['value']
        if signal_value == 'BUY':
            trade_op['systemAction'] = SystemAction.ACTION_BUY
        elif signal_value == 'SELL':
            trade_op['systemAction'] = SystemAction.ACTION_SELL
        elif signal_value == 'FLAT':
            trade_op['systemAction'] = SystemAction.ACTION_FLAT
        elif signal_value == 'HOLD':
            trade_op['systemAction'] = SystemAction.ACTION_HOLD
        else:
            trade_op['systemAction'] = SystemAction.NOACTION
            
        # Preparo i parametri operativi
        self._state['target_qty'] = self.get_system_param(params, 'qty')
        self._state['current_position'] = position
        
        self.consoleLog(f"FUTM inizializzato: {signal_value} qty={self._state['target_qty']}", 
                       Severity.INFO, import_uid)
        return True
    
    def do_process_data(self, frame_data: dict, portfolio: dict) -> Tuple[SystemAction, float, float]:
        """Logica FUTM: esegue il segnale configurato"""
        # FUTM è un sistema "one-shot": esegue il segnale una volta e si completa
        if self.is_completed():
            return SystemAction.NOACTION, 0, 0
            
        # Eseguo solo su candele complete
        if not frame_data['timeFrameEnd']:
            return SystemAction.NOACTION, 0, 0
            
        # Recupero l'azione configurata
        trade_op = self._state['tradeOp']
        action = trade_op.get('systemAction', SystemAction.NOACTION)
        qty = self._state.get('target_qty', 0)
        
        # Calcolo stop price (esempio: 2% dal prezzo corrente)
        stop_price = 0
        if action in [SystemAction.ACTION_BUY, SystemAction.ACTION_SELL]:
            stop_percentage = 0.02
            if action == SystemAction.ACTION_BUY:
                stop_price = frame_data['close'] * (1 - stop_percentage)
            else:
                stop_price = frame_data['close'] * (1 + stop_percentage)
        
        # Dopo aver eseguito il segnale, completo il sistema
        if action != SystemAction.NOACTION:
            self.consoleLog(f"Eseguo segnale: {action.name} qty={qty}", Severity.INFO)
            # Il sistema si completerà automaticamente dopo l'esecuzione dell'ordine
        
        return action, qty, stop_price
    
    def do_resume_system(self, frame_data: List[dict], portfolio: dict,
                        chart: Any, state: dict, log: list,
                        time_now: int, import_uid: str) -> bool:
        """Ripresa FUTM dopo crash"""
        # Ripristino stato salvato
        if state:
            self._state.update(state)
            
        # FUTM è semplice, non ha indicatori complessi da ricalcolare
        self.consoleLog("FUTM ripristinato correttamente", Severity.INFO, import_uid)
        return True


"""
VANTAGGI DEL FRAMEWORK BASESYSTEM:

1. SEPARAZIONE RESPONSABILITÀ: 
   - Framework gestisce: stato, ordini, logging, recovery
   - Sistema gestisce: solo logica di trading specifica

2. CONSISTENZA:
   - Tutti i sistemi hanno stesso ciclo vita
   - Stesso pattern di error handling
   - Logging standardizzato

3. ROBUSTEZZA:
   - State persistence automatico
   - Recovery trasparente dopo crash
   - Gestione ordini centralizzata

4. SEMPLICITÀ SVILUPPO:
   - Per creare nuovo sistema: implementi 4 metodi abstract
   - Framework gestisce tutta la complessità
   - Focus sulla logica, non sull'infrastruttura

5. DEBUGGING:
   - Logging strutturato e consistente
   - Stato sempre tracciabile
   - Import UID per correlazione eventi

PATTERN ARCHITETTURALE:
Template Method Pattern + Strategy Pattern + State Pattern

Il risultato: posso scrivere nuovi sistemi di trading in pochissimo tempo
concentrandomi solo sulla logica specifica, mentre tutto il resto è automatico.
"""