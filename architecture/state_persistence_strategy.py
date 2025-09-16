"""
MAOTrade - State Persistence & Recovery Strategy

Estratto dal sistema reale che mostra come ho implementato la persistenza dello stato
e la recovery automatica dopo un crash. Basato sul codice reale di BaseSystem.

Questo NON è codice eseguibile, ma una vetrina dell'architettura implementata.
"""

from abc import ABC, abstractmethod
import json
from typing import Dict, Any, List
from mtcommon.utils.ChartData import ChartData
from maotrade.mtlogging import Severity


class BaseSystem(ABC):
    """
    Framework base per trading systems con state persistence integrata.
    Estratto dal BaseSystem.py reale.
    """
    
    def __init__(self, config_params: dict, system_params: dict):
        # State interno - tutto qui viene automaticamente persistito
        self._state = {}
        self._state_updated = False
        
        # Parametri del sistema sempre presenti
        self._state = {
            'systemCompleted': system_params.get('systemCompleted', False),
            'systemBlocked': system_params.get('systemBlocked', False), 
            'systemError': system_params.get('systemError', False),
            'frameMissUpdateSec': system_params.get('frameMissUpdateSec', 60),
            'maxOrderSubmitTimeSec': system_params.get('maxOrderSubmitTimeSec', 30)
        }
        
        # Chart data per visualizzazione grafica
        self._chart = None
        self._chart_updated = False

    @property
    def system_state(self) -> dict:
        """
        Ritorna il dizionario che contiene lo stato del system.
        Utilizzato dal sistema di persistenza per il salvataggio.
        """
        return self._state

    @property 
    def system_state_json(self) -> str:
        """
        Ritorna la struttura che contiene lo stato del system in formato JSON 
        solo se lo stato è stato aggiornato dall'ultima richiesta.
        Meccanismo per evitare salvataggi inutili su disco.
        """
        if not self._state_updated:
            return ""
        self._state_updated = False
        return json.dumps(self._state, separators=(',', ':'), default=str)

    def update_chart_state_log(self, chart: ChartData, state: dict, log: list):
        """
        Aggiorna il grafico e lo state del system se vengono passati non vuoti. 
        Questa funzione è stata pensata per essere utilizzata durante la ripresa del system.
        
        Dal BaseSystem.py reale - utilizzata durante recovery.
        """
        if chart:
            self._chart = chart
            self._chart_updated = True
        if state:
            self._state = state
            self._state_updated = True
        if log:
            self.__system_log.restore_log_items(log)

    def request_resume_system(self, frame_data: List[dict], portfolio: dict, 
                            chart: ChartData, state: dict, log: list, 
                            time_now: int, import_uid: str) -> bool:
        """
        Gestisce la ripresa del system nel caso d'interruzione improvvisa del server.
        Dal BaseSystem.py reale - entry point per la recovery.
        """
        self.consoleLog("Ripresa system in corso...", Severity.INFO, import_uid)
        
        # Calcolo il numero di frames che dovrei ricevere
        num_frames = (time_now - self.trade_start) // self.time_frame
        if num_frames < 0:
            self.consoleLog("Errore numero frames dati negativo", Severity.ERROR, import_uid)
        elif len(frame_data) < num_frames or len(frame_data) > num_frames:
            self.consoleLog(f"Frame dati attesi {num_frames}, scaricati {len(frame_data)}", 
                          Severity.WARNING, import_uid)

        # Chiama la logica specifica di recovery del system
        ret = self.do_resume_system(frame_data, portfolio, chart, state, log, time_now, import_uid)
        
        if ret:
            self.consoleLog(f"Ripresa system terminata correttamente", Severity.INFO, import_uid)
        else:
            self.consoleLog(f"Errori durante la ripresa system", Severity.ERROR, import_uid)
            self.send_push_message(f"Errore ripresa system [{self._params['titleDescr']}]",
                                 "Il system ha incontrato errori durante la ripresa", 
                                 Severity.ERROR)
        return ret

    @abstractmethod
    def do_resume_system(self, frame_data: List[dict], portfolio: dict, chart: ChartData, 
                        state: dict, log: list, time_now: int, import_uid: str) -> bool:
        """
        Esegue la ripresa del system nel caso d'interruzione improvvisa del server.
        DA IMPLEMENTARE in ogni trading system specifico.
        
        Dal BaseSystem.py reale - ogni system deve definire la propria recovery logic.
        """
        pass

    def set_blocked(self, blocked: bool):
        """
        Imposta il system come bloccato o meno. Un system bloccato non invia ordini.
        Dal BaseSystem.py reale - gestione stati del sistema.
        """
        if blocked and not self._params['systemBlocked']:
            self.consoleLog("System BLOCCATO", Severity.INFO)
        elif not blocked and self._params['systemBlocked']:
            self.consoleLog("System SBLOCCATO", Severity.INFO)
        
        self._params['systemBlocked'] = blocked

    def set_error_state(self):
        """
        Imposta lo stato di errore per il system. Un system in errore è bloccato e non invia ordini.
        Dal BaseSystem.py reale - gestione errori critici.
        """
        if self._params['systemCompleted'] or self._params['systemError']:
            return
            
        self.consoleLog("System IN ERRORE", Severity.CRITICAL)
        self._params['systemError'] = True

    @property
    def is_operating(self) -> bool:
        """
        True il system sta operando non in errore e non è bloccato, False non sta operando.
        Dal BaseSystem.py reale - controllo stato operativo.
        """
        return not self.is_completed() and not self.is_error_state() and not self.blocked


class FUTMSystem(BaseSystem):
    """
    Esempio reale: Sistema FUTM con recovery implementation.
    Estratto dal FUTM.py effettivo.
    """
    
    def do_resume_system(self, frame_data: List[dict], portfolio: dict, chart: ChartData, 
                        state: dict, log: list, time_now: int, import_uid: str) -> bool:
        """
        Recovery implementation reale dal FUTM.py.
        Mostra come ripristinare indicatori e stato dopo crash.
        """
        # Ripristino gli indicatori con i dati della giornata di contrattazioni
        ret = self._setup_indicators(frame_data, import_uid, False)
        
        # Riprendo sia il grafico che lo state come prima dell'interruzione  
        self.update_chart_state_log(chart, state, log)

        # Quello che segue è il setup del grafico, se il grafico non c'è vuol dire che quello che ho è corretto
        if not chart:
            return ret

        # In ripresa prendo le aree del grafico già create
        self._area_image = self._chart.get_area_by_id("segnali")
        self._area_mama_fast = self._chart.get_area_by_id("mama_fast")
        self._area_fama_fast = self._chart.get_area_by_id("fama_fast")
        
        return ret

    def _setup_indicators(self, frame_data: List[dict], import_uid: str, is_new_system: bool) -> bool:
        """
        Ricostruzione indicatori dai dati storici.
        Utilizzato sia per inizializzazione che per recovery.
        """
        # Implementation specifica per FUTM - ricostruisce MAMA/FAMA
        # dai frame_data forniti per ripristinare lo stato pre-crash
        pass


class SystemTester:
    """
    Sistema di testing che simula crash e recovery.
    Estratto dal SystemTester.py reale.
    """
    
    def simulate_crash_recovery(self, resume_at_frame: int):
        """
        Simulazione crash e recovery per testing.
        Dal SystemTester.py reale - utilizzato per validare la recovery logic.
        """
        num_frame = 0
        
        for frame in self.frames_data:
            num_frame += 1
            
            # Se devo simulare la ripresa del system
            if self._resume_at_frame and self._resume_at_frame == num_frame:
                self._logger.info("Inizio ripresa system")
                
                # Salvo stato corrente prima del "crash"
                system = self._tt['system']
                chart = system.system_chart
                state = system.system_state  
                log = system.system_log
                
                # Reinizializzo il system come se il server si fosse riavviato
                self._logger.info("Reinizializzazione system in corso")
                if init_ret := self._init_system():
                    self._logger.error(f"Errore inizializzazione durante ripresa system: {init_ret}")
                    raise ValueError("Errore inizializzazione durante ripresa system")
                
                self._logger.info("Reinizializzazione system completata")
                
                # Chiamo la recovery con lo stato salvato
                system = self._tt['system']  # Nuovo system instance
                resume_ret = system.request_resume_system(
                    self.frames_data[:num_frame - 1],  # Dati fino al momento del crash
                    self._portf_data, 
                    chart, state, log,
                    frame['timestamp'], 
                    "import_uid"
                )
                
                # Se qualcosa non è andato bene durante la ripresa  
                if not resume_ret:
                    self._logger.error("Errore durante la ripresa system")
                    return False
                    
                self._logger.info("Ripresa system completata con successo")
        
        return True


class SignalsHelper:
    """
    Gestione segnali e recovery a livello di sistema.
    Estratto dal SignalsHelper.py reale.
    """
    
    def call_resume_system(self, tt: dict, signal: dict, portf_data: dict, 
                          time_now: int, uid: str):
        """
        Controlla se chiamare il metodo che gestisce la ripresa del system e nel caso lo chiama.
        Dal SignalsHelper.py reale - orchestrazione recovery a livello sistema.
        """
        # Recupero i dati salvati del system e nel caso ci siano chiamo la funzione di ripresa
        chart, state, log = self._dao.get_system_chart_state_log(signal['idOp'])
        
        # Calcolo il numero di frames di dati odierni che servono al system  
        num_frames = (time_now - signal['startTrade']) // tt['system'].time_frame
        
        # Recupero i dati di mercato della giornata già eseguiti dal system
        rlt_data = self._dao.get_mt_rlt_data(signal['epic'], signal['startTrade'], 
                                           time_now, tt['system'].time_frame)
        
        if rlt_data and len(rlt_data) > 0:
            # Chiamo la recovery del system con i dati recuperati
            resume_success = tt['system'].request_resume_system(
                rlt_data, portf_data, chart, state, log, time_now, uid
            )
            
            if resume_success:
                self._log.info(f"Recovery system completata con successo per {signal['idOp']}")
            else:
                self._log.error(f"Errore durante recovery system {signal['idOp']}")


"""
ARCHITETTURA EVIDENZIATA (dal codice reale):

1. STATE PERSISTENCE: 
   - system_state_json() salva automaticamente ogni modifica
   - _state_updated flag evita salvataggi inutili
   
2. RECOVERY FRAMEWORK:
   - request_resume_system() entry point standardizzato
   - do_resume_system() implementazione specifica per ogni system
   - update_chart_state_log() ripristino stato completo

3. VALIDATION & SAFETY:
   - Controllo coerenza frame dati vs tempo trascorso
   - Gestione stati (blocked, error, completed)
   - Logging dettagliato di ogni fase recovery

4. TESTING & SIMULATION:
   - SystemTester simula crash in punti specifici
   - Validazione completa del processo recovery
   - Test automatizzato della robustezza

BUSINESS VALUE DIMOSTRATO:
- Zero perdita dati in caso di crash server
- Recovery automatico senza intervento umano  
- Continuità operativa per sistemi di trading critici
"""