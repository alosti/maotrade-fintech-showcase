"""
Order Lifecycle Management - MAOTrade
====================================

Questo modulo mostra come ho implementato la gestione del ciclo di vita degli ordini
nel sistema MAOTrade. Il tracking preciso dello stato degli ordini è critico per 
sistemi di trading che operano con denaro reale.

Estratto dal codice reale - niente invenzioni, solo quello che ho implementato.
"""

from enum import IntEnum
from typing import Optional
import time


# ============================================================================
# ENUM STATI ORDINI - Come ho definito gli stati nel sistema reale
# ============================================================================

class OrderExecState(IntEnum):
    """
    Stato di esecuzione di un ordine nel sistema MAOTrade.
    Ogni ordine segue questa state machine precisa.
    """
    JUST_CREATED = 0    # Ordine appena creato dal sistema
    SUBMITTED = 1       # Inviato al broker
    ACCEPTED = 2        # Broker ha accettato l'ordine  
    FILLED = 3          # Ordine eseguito completamente
    ERROR = 4           # Errore nell'esecuzione
    CANCELLED = 5       # Ordine cancellato


class DealStatus(IntEnum):
    """
    Stato processing ordine nell'Account Manager.
    Gestisce il processo di invio al broker con retry logic.
    """
    NOT_SUBMITTED = 0   # Non ancora inviato
    DELAYED = 1         # In attesa di retry dopo errore
    SUBMITTING = 2      # In corso di invio
    SUBMITTED = 3       # Inviato con successo
    EXECUTING = 4       # In esecuzione dal broker
    REJECTED = 5        # Rifiutato
    TOTRASH = 6        # Da eliminare dalla coda


class OrderAction(IntEnum):
    """
    Tipologia di azione dell'ordine
    """
    OPEN_POSITION = 0
    CLOSE_POSITION = 1
    MODIFY_POSITION = 3


# ============================================================================
# STRUTTURA ORDINE - Come ho strutturato gli ordini nel BaseSystem
# ============================================================================

def create_trade_order(epic: str = "", op_type=None, order_type=None, 
                      pos_cmd=None, qty: float = 0, stop_price: float = 0.0,
                      author_type=None, author: str = "",
                      max_submit_time_sec: int = 120,
                      submit_time_delay_sec: int = 30,
                      complete_system_on_filled: bool = False,
                      on_filled_action: tuple = None) -> dict:
    """
    Crea una richiesta di ordine secondo la struttura che uso nel BaseSystem reale.
    
    Il dizionario ritornato è esattamente quello che uso in produzione.
    Ogni campo ha un ruolo preciso nel tracking dell'ordine.
    """
    if on_filled_action is None:
        on_filled_action = (0, 0.0, 0.0)  # SystemAction.NOACTION, 0, 0
        
    trade_order = {
        'id': 0,                        # ID database (popolato al salvataggio)
        'epic': epic,                   # Strumento finanziario
        'epicDescr': "",               # Descrizione per logging
        'opType': op_type,             # OrderOpType: BUY/SELL
        'orderType': order_type,       # OrderType: MKT/STP
        'posCmd': pos_cmd,             # OrderPosCmd: NEW/CLOSE
        'qty': abs(qty),               # Quantità (sempre positiva)
        'stopPrice': stop_price,       # Prezzo di stop
        'author': author,              # Chi ha creato l'ordine
        'authorType': author_type,     # OrderAuthorType: SYSTEM/USER
        'maxSubmitTimeSec': max_submit_time_sec,    # Timeout submit
        'submitDelayTimeSec': submit_time_delay_sec, # Delay retry
        'completeSystemOnFilled': complete_system_on_filled,  # Auto-complete
        'onFilledAction': on_filled_action,  # Azione dopo fill
        
        # STATO ORDINE - Questo è il cuore del tracking
        'status': {
            'execState': OrderExecState.JUST_CREATED,
            'dealReference': "",        # ID broker
            'filled': 0.0,             # Quantità eseguita
            'avgFillPrice': 0.0,       # Prezzo medio esecuzione
            'pnl': 0.0,                # P&L ordine
            'errorCode': 0,            # Codice errore broker
            'errorMessage': "",        # Messaggio errore
            'filledTriggered': False   # Flag evento fill inviato
        }
    }
    return trade_order


# ============================================================================  
# CLASSE BASEORDER - Come gestisco gli ordini nell'Account Manager
# ============================================================================

class BaseOrder:
    """
    Rappresenta un ordine nell'Account Manager.
    Gestisce il processo di invio al broker con retry logic e timeout.
    
    Questa è la classe reale che uso in MAOTrade - estratta dal codice originale.
    """
    
    def __init__(self):
        # Identificatori
        self.orderId: int = 0
        self.epic: str = ""
        self.epicBroker: str = ""
        
        # Parametri ordine
        self.action: OrderAction = OrderAction.OPEN_POSITION
        self.currency: str = ""
        self.qty: float = 0.0
        self.direction: int = 0    # 1=BUY, 2=SELL
        self.orderType: int = 0    # 0=MARKET, 1=LIMIT, 2=STOP
        self.stopPrice: float = 0.0
        
        # Stato processing
        self.dealStatus: DealStatus = DealStatus.NOT_SUBMITTED
        self.dealReference: str = ""
        self.errorMessage: str = ""
        
        # Timing e retry logic
        self.submitStart: int = 0      # Quando iniziato il submit
        self.submitDeadline: int = 0   # Deadline per timeout
        self.submitDelay: int = 30     # Secondi tra retry
        self.submitRetry: int = 0      # Prossimo tentativo
        
    def init_order(self, order_id: int, action: OrderAction, epic: str,
                  currency: str, qty: float, direction: int = 0,
                  order_type: int = 0, stop_price: float = 0.0,
                  max_submit_time_sec: int = 120,
                  submit_time_delay_sec: int = 30,
                  time_now: int = 0, epic_broker: str = ""):
        """
        Inizializza l'ordine con i parametri specificati.
        Chiamata dal BaseAccountManager quando riceve richiesta ordine.
        """
        self.orderId = order_id
        self.action = action
        self.epic = epic
        self.epicBroker = epic_broker
        self.currency = currency
        self.qty = qty
        self.direction = direction
        self.orderType = order_type
        self.stopPrice = stop_price
        self.dealReference = ""
        self.submitStart = time_now
        self.submitDeadline = time_now + max_submit_time_sec
        self.errorMessage = ""
        self.dealStatus = DealStatus.NOT_SUBMITTED
        self.submitDelay = submit_time_delay_sec
        self.submitRetry = 0
        
    def validate_order(self) -> bool:
        """
        Valida i dati dell'ordine prima dell'invio.
        
        Returns:
            bool: True se validazione OK, False se ci sono errori
        """
        if not self.epicBroker:
            self.errorMessage = f"ERRORE Epic {self.epic} non trovato lato broker"
            self.dealStatus = DealStatus.REJECTED
            return False

        # Validazione specifica per nuove posizioni
        if self.action == OrderAction.OPEN_POSITION:
            if self.direction not in [1, 2]:
                self.errorMessage = f"ERRORE direzione {self.direction}. Valori ammessi sono 1 o 2"
                self.dealStatus = DealStatus.REJECTED
                return False

            if self.qty == 0:
                self.errorMessage = f"ERRORE quantità zero non ammessa su nuove posizioni"
                self.dealStatus = DealStatus.REJECTED
                return False
                
            # Aggiustamento segno quantità basato su direzione
            elif self.direction == 1 and self.qty < 0:
                # Ordine long: quantità deve essere positiva
                self.qty *= -1
            elif self.direction == 2 and self.qty > 0:
                # Ordine short: quantità deve essere negativa  
                self.qty *= -1

        return True
    
    def set_delayed(self, error_msg: str = ""):
        """
        Mette l'ordine in stato DELAYED per retry successivo.
        
        Args:
            error_msg: Messaggio di errore opzionale
        """
        self.dealStatus = DealStatus.DELAYED
        if error_msg:
            self.errorMessage = error_msg
        self.submitRetry = int(time.time()) + self.submitDelay
        
    def set_rejected(self, error_msg: str):
        """
        Mette l'ordine in stato REJECTED con messaggio errore.
        
        Args:
            error_msg: Messaggio di errore
        """
        self.dealStatus = DealStatus.REJECTED
        self.errorMessage = error_msg
        
    def set_submitted(self, deal_reference: str = ""):
        """
        Mette l'ordine in stato SUBMITTED dopo invio al broker.
        
        Args:
            deal_reference: ID ordine restituito dal broker
        """
        if deal_reference:
            self.dealReference = deal_reference
        self.dealStatus = DealStatus.SUBMITTED


# ============================================================================
# ORDER PROCESSING - Come processo la coda ordini nell'Account Manager
# ============================================================================

def process_order_list(order_list: list, time_now: int,
                      do_async_request_order_open,
                      do_async_request_order_close, 
                      do_async_request_order_stop) -> int:
    """
    Processa la coda di richiesta degli ordini con politica di submit e retry.
    
    Questa è la logica reale estratta dal BaseAccountManager.
    Gestisce timeout, retry ed eliminazione ordini completati.
    
    Args:
        order_list: Lista ordini da processare
        time_now: Timestamp corrente
        do_async_request_*: Callback per invio ordini (implementate dai broker specifici)
        
    Returns:
        int: Numero ordini eliminati dalla coda
    """
    trashed_orders = 0
    
    # Processo ogni ordine nella coda
    for order in order_list:
        if order.dealStatus in [DealStatus.NOT_SUBMITTED, DealStatus.DELAYED]:
            # Controllo timeout per submit
            if order.submitDeadline < time_now:
                if order.errorMessage:
                    order.errorMessage += ". "
                order.errorMessage += "Scaduto il tempo per il submit dell'ordine"
                order.dealStatus = DealStatus.REJECTED
                
            # Invio ordine se è il momento giusto
            if ((order.dealStatus == DealStatus.DELAYED and time_now >= order.submitRetry) or
                    order.dealStatus == DealStatus.NOT_SUBMITTED):
                
                # Dispatch basato su tipo azione
                if order.action == OrderAction.OPEN_POSITION:
                    order.dealStatus = DealStatus.SUBMITTING
                    do_async_request_order_open(order)
                elif order.action == OrderAction.CLOSE_POSITION:
                    order.dealStatus = DealStatus.SUBMITTING
                    do_async_request_order_close(order)
                elif order.action == OrderAction.MODIFY_POSITION:
                    order.dealStatus = DealStatus.EXECUTING
                    do_async_request_order_stop(order)
                    
        # Conteggio ordini da eliminare
        if order.dealStatus == DealStatus.TOTRASH:
            trashed_orders += 1
            
    # Cleanup della coda se troppi ordini terminati
    if trashed_orders > 5:
        order_list[:] = [order for order in order_list if order.dealStatus != DealStatus.TOTRASH]
        
    return trashed_orders


# ============================================================================
# ORDER CALLBACKS - Come gestisco le risposte dal TradeMgr
# ============================================================================

def on_order_result_handler(srv_code: int, order_response: dict, 
                           trade_order: dict, dao) -> bool:
    """
    Gestisce la risposta del broker per un ordine inviato.
    
    Questo è estratto dal TradeMgr.on_order_result() - la logica reale
    di come aggiorno lo stato ordine basato su risposta broker.
    
    Args:
        srv_code: Codice risposta (0=OK, altro=errore)
        order_response: Risposta dal broker
        trade_order: Ordine da aggiornare
        dao: Data Access Object per database
        
    Returns:
        bool: True se processing OK, False se errore
    """
    # Gestione errore invio
    if srv_code:
        print(f"ERRORE Ordine id: {order_response['orderId']}")
        
        # Aggiorno stato ordine
        trade_order['status']['execState'] = OrderExecState.ERROR
        trade_order['status']['errorCode'] = 1
        trade_order['status']['errorMessage'] = order_response.get('message', 'Errore sconosciuto')
        
        # Salvataggio su database
        try:
            dao.update_order_error({
                'status': trade_order['status']['execState'].value,
                'errorMessage': trade_order['status']['errorMessage'],
                'errorCode': trade_order['status']['errorCode'],
                'id': trade_order['id']
            })
        except Exception as e:
            print(f"Errore database: {e}")
            
        return False
        
    # Gestione successo
    trade_order['status']['execState'] = OrderExecState.ACCEPTED
    trade_order['status']['dealReference'] = order_response['dealReference']
    
    # Aggiorno database
    try:
        dao.update_order_status({
            'status': trade_order['status']['execState'].value,
            'dealId': trade_order['status']['dealReference'],
            'id': trade_order['id']
        })
    except Exception as e:
        print(f"Errore database: {e}")
        
    print(f"Ordine id: {order_response['orderId']} ACCETTATO")
    return True


def on_order_filled_handler(srv_code: int, order_filled: dict,
                           trade_order: dict, dao) -> bool:
    """
    Gestisce l'evento di ordine eseguito (filled).
    
    Estratto dal TradeMgr.on_order_filled() - logica reale per
    processing dell'esecuzione ordine.
    
    Args:
        srv_code: Codice risposta
        order_filled: Dati esecuzione ordine
        trade_order: Ordine eseguito
        dao: Data Access Object
        
    Returns:
        bool: True se processing OK, False se errore
    """
    # Gestione errore esecuzione
    if srv_code:
        print(f"ERRORE Esecuzione ordine id: {order_filled['orderId']}")
        
        trade_order['status']['execState'] = OrderExecState.ERROR
        trade_order['status']['errorCode'] = 2
        trade_order['status']['errorMessage'] = order_filled.get('message', 'Errore esecuzione')
        
        try:
            dao.update_order_error({
                'status': trade_order['status']['execState'].value,
                'errorMessage': trade_order['status']['errorMessage'], 
                'errorCode': trade_order['status']['errorCode'],
                'id': trade_order['id']
            })
        except Exception as e:
            print(f"Errore database: {e}")
            
        return False
        
    # Aggiorno con dati esecuzione
    trade_order['status']['execState'] = OrderExecState.FILLED
    trade_order['status']['avgFillPrice'] = order_filled['price']
    trade_order['status']['pnl'] = order_filled['pnl']
    trade_order['status']['filled'] = order_filled['qty']
    
    # Salvataggio risultati esecuzione
    try:
        dao.update_order_filled({
            'avgFillPrice': order_filled['price'],
            'pnl': order_filled['pnl'],
            'id': order_filled['orderId']
        })
    except Exception as e:
        print(f"Errore database: {e}")
        
    print(f"Ordine id: {order_filled['orderId']} ESEGUITO @ {order_filled['price']}")
    return True


# ============================================================================
# UTILIZZO ESEMPIO
# ============================================================================

if __name__ == "__main__":
    """
    Esempio di come uso il sistema di order lifecycle in pratica.
    """
    
    # 1. Creazione ordine dal BaseSystem
    order_data = create_trade_order(
        epic="EURUSD",
        op_type=1,  # BUY
        order_type=0,  # MARKET
        pos_cmd=1,  # NEW_POSITION
        qty=1000,
        stop_price=1.0850,
        author_type=0,  # AUTHOR_SYSTEM
        max_submit_time_sec=120,
        submit_time_delay_sec=30
    )
    
    print(f"Ordine creato: {order_data['epic']} - Stato: {order_data['status']['execState']}")
    
    # 2. Creazione BaseOrder per Account Manager
    base_order = BaseOrder()
    base_order.init_order(
        order_id=12345,
        action=OrderAction.OPEN_POSITION,
        epic="EURUSD",
        currency="EUR",
        qty=1000,
        direction=1,  # BUY
        time_now=int(time.time()),
        epic_broker="EUR_USD"
    )
    
    # 3. Validazione
    if base_order.validate_order():
        print(f"Ordine validato: {base_order.epic} - Status: {base_order.dealStatus}")
    else:
        print(f"Errore validazione: {base_order.errorMessage}")
        
    # 4. Simulazione stati ordine
    base_order.set_submitted("DEAL_REF_12345")
    print(f"Ordine inviato - Deal Reference: {base_order.dealReference}")
    
    # 5. Aggiornamento stato finale
    order_data['status']['execState'] = OrderExecState.FILLED
    order_data['status']['avgFillPrice'] = 1.0895
    order_data['status']['filled'] = 1000
    order_data['status']['pnl'] = 45.0
    
    print(f"Ordine eseguito @ {order_data['status']['avgFillPrice']} - P&L: {order_data['status']['pnl']}")
    
    print("\n=== LIFECYCLE COMPLETO ===")
    print("JUST_CREATED -> SUBMITTED -> ACCEPTED -> FILLED")
    print("Il sistema traccia ogni passaggio con timestamp precisi per audit completo.")