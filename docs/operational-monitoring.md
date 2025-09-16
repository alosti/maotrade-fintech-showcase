# **MAOTrade - Sistema di Monitoring**

## **Contesto e Obiettivi**

MAOTrade è una piattaforma di trading automatizzato composta da servizi Python distribuiti su container Docker. Il sistema richiede un monitoring in tempo reale per garantire continuità operativa durante le sessioni di trading, dove anche pochi minuti di downtime possono comportare perdite finanziarie significative.

## **Architettura di Monitoring**

Il sistema utilizza Nagios per il controllo dell'infrastruttura, configurato per distinguere chiaramente tra diversi livelli di criticità operativa.

### **Componenti Monitorati**

**Servizi Core Trading:**

- **MAOApi**: API REST per gestione ordini e dati di mercato
- **MAOData**: elaborazione algoritmica dei dati finanziari  
- **MAOPod**: orchestrazione dei motori di trading containerizzati
- **Fluentd**: aggregazione log per audit e troubleshooting

**Infrastruttura Base:**

- Database MySQL/MongoDB per persistenza dati
- Docker daemon per gestione container
- Risorse sistema (CPU, RAM, disco, rete)
- Controlli sicurezza e accessi SSH

## **Strategia di Alert e Prioritizzazione**

Il sistema implementa una logica di alert basata sull'impatto business invece che sulla tradizionale classificazione tecnica.

### **Livelli di Criticità**

**🔴 Tier 1 - Trading Critical** (alert ogni 15-30 minuti): Servizi che impattano direttamente la capacità di trading. Un downtime di questi componenti blocca le operazioni finanziarie.

**🟡 Tier 2 - Infrastructure** (alert ogni 60 minuti): Componenti di supporto che potrebbero causare degradazione delle performance ma non blocco immediato.

**🟢 Tier 3 - Support** (alert ogni 4-24 ore): Servizi accessori che non impattano le operazioni core.

### **Gestione dei Falsi Positivi**

I controlli sono configurati per distinguere tra servizi systemd (che o funzionano o sono down) e operazioni che possono avere stati intermedi. I servizi Python ricevono alert immediati al primo fallimento, mentre i job di elaborazione hanno un massimo di un retry prima dell'escalation.

## **Ottimizzazioni Specifiche per Trading**

### **Bilanciamento del Carico di Monitoring**

I controlli sono distribuiti temporalmente per evitare picchi di carico che potrebbero interferire con le operazioni di trading. I check più critici sono sfalsati di 1-2 minuti per distribuire il carico computazionale.

### **Dependency Management**

Il sistema implementa dipendenze logiche per evitare spam di alert. Se MySQL va down, gli alert per i servizi che ne dipendono vengono silenziati, permettendo di concentrarsi sulla causa root del problema.

### **Controlli Predittivi**

Sono implementati controlli su processi zombie e stati di sleep non interrompibili, che spesso precedono crash di sistema in ambienti ad alto carico come quelli di trading.

## **Risultati e Benefici**

### **Risposta più veloce**

La classificazione per criticità business permette di identificare immediatamente se un problema impatta il trading o è un issue secondario. Un operatore può distinguere in 5 secondi se deve interrompere il sonno per un'emergenza o se può aspettare il mattino.

### **Riduzione dei Falsi Allarmi**

La configurazione differenziata per tipo di servizio ha ridotto significativamente gli alert non actionable, migliorando la fiducia del team nel sistema di monitoring.

### **Troubleshooting più Efficace**

L'aggregazione dei log tramite Fluentd, classificata come servizio critico, garantisce che in caso di problemi ci siano sempre i dati necessari per la diagnosi, aspetto fondamentale in un ambiente finanziario dove ogni evento deve essere tracciabile.

## **Considerazioni Tecniche**

La soluzione è stata implementata su un server dedicato i7 con 32GB RAM, con controlli distribuiti per mantenere l'overhead di monitoring sotto il **2%** delle risorse sistema. Il sistema può scalare facilmente aggiungendo server satellite senza modifiche architetturali significative.

La configurazione privilegia la **semplicità operativa** rispetto alla complessità tecnica, principio fondamentale quando si devono prendere decisioni rapide su sistemi che gestiscono denaro reale.

---

## **Appendice Tecnica - Dettaglio Configurazioni per Service Group**

### **🔴 Trading-Critical Services**

**Finalità:** Servizi che impattano direttamente la capacità di eseguire operazioni di trading.

**Servizi monitorati:**

| Servizio | Check Interval | Max Attempts | Rinotifica |
|----------|----------------|--------------|------------|
| **MAOApi service** | 8 min | 1 | 15 min |
| **MAOData service** | 8 min | 1 | 15 min |
| **MAOPod service** | 8 min | 1 | 15 min |
| **MAOData jobs** | 6 min | 1 retry | 30 min |
| **MAOPod pods** | 6 min | 1 retry | 30 min |
| **Docker Daemon** | 5 min | 1 | 15 min |
| **Fluentd service** | 8 min | 1 | 15 min |

**Politica di alert:** Zero tolleranza per downtime. Alert immediati per servizi systemd (`max_check_attempts=1`) e massimo un retry per job di elaborazione. Rinotifiche aggressive fino a risoluzione.

**Razionale:** Un fallimento di questi componenti blocca immediatamente le operazioni di trading. Il costo di un falso positivo è inferiore al rischio di perdere opportunità di mercato.

### **🔵 Database Services**

**Finalità:** Controlli di performance e disponibilità dei sistemi di persistenza dati.

**Servizi monitorati:**

| Servizio | Check Interval | Soglie | Rinotifica |
|----------|----------------|---------|------------|
| **MYSQL Connection time** | 5 min | - | 30 min |
| **MYSQL Connections** | 6 min | - | 60 min |
| **MYSQL Open files** | 7 min | 7000/8500 | 60 min |
| **MYSQL Index usage** | 10 min | 90%/80% | 60 min |
| **MYSQL Slow queries** | 8 min | 0.2/1 | 60 min |
| **MongoDB maologs** | 9 min | - | 60 min |

**Politica di alert:** Connection time ha priorità massima (30 min rinotifica) mentre i controlli di performance hanno cadenza oraria. Le soglie sono calibrate per early warning prima che l'impatto diventi critico.

**Razionale:** Il database è il collo di bottiglia principale. La distinzione tra controlli di disponibilità e performance permette di prioritizzare correttamente gli interventi.

### **🟡 Infrastructure Services**

**Finalità:** Monitoring delle risorse di sistema e della stabilità della piattaforma.

**Servizi monitorati:**

| Servizio | Check Interval | Soglie | Rinotifica |
|----------|----------------|---------|------------|
| **Root/Home Partition** | 3-4 min | 20%/10%, 30%/20% | 60 min |
| **Current Load** | 3 min | - | 60 min |
| **Network traffic** | 5 min | 2048K/4096K | 60 min |
| **Swap Usage** | 4 min | 30%/15% | 60 min |
| **Zombie Processes** | 3 min | 1/5 | 30 min |
| **Uninterruptible Sleep Processes** | 3 min | 1/3 | 30 min |
| **Total Processes** | 8 min | 250/400 | 2 ore |

**Politica di alert:** Controlli ad alta frequenza per detection rapida, ma rinotifiche meno aggressive. I controlli sui processi anomali (zombie/D-state) hanno priorità maggiore perché spesso precursori di crash di sistema.

**Razionale:** L'infrastruttura deve essere stabile per supportare il trading, ma problemi non critici possono essere gestiti senza urgenza estrema.

### **🔒 Security & Access Services**

**Finalità:** Controllo accessi e sicurezza del sistema.

**Servizi monitorati:**

| Servizio | Check Interval | Soglie | Rinotifica |
|----------|----------------|---------|------------|
| **Current Users** | 10 min | 2/5 | 4 ore |
| **SSH** | 5 min | - | 60 min |
| **SSH Failed Logins** | 15 min | 300/1500 | 2 ore |
| **Fail2ban service** | 10 min | alert immediato | 60 min |

**Politica di alert:** Bilanciamento tra sicurezza e operatività. SSH failure ha detection rapida ma rinotifiche moderate per evitare spam durante attacchi automatizzati. Fail2ban ha alert immediati perché un suo malfunzionamento compromette istantaneamente la protezione da attacchi brute force.

**Razionale:** La sicurezza è critica per una piattaforma di trading accessibile da remoto. Fail2ban protegge da attacchi brute force SSH ed è sufficiente per garantire il corretto funzionamento del sistema di protezione. Il controllo si concentra sulla disponibilità del servizio di protezione attiva piuttosto che sui meccanismi sottostanti, evitando ridondanze e complessità inutili.

### **🟢 Support Services**

**Finalità:** Servizi accessori che non impattano direttamente il core business.

**Servizi monitorati:**

| Servizio | Check Interval | Max Attempts | Rinotifica |
|----------|----------------|--------------|------------|
| **MAOAdmin** | 20 min | 2 | 4 ore |
| **Postfix Mail server/queue** | 10-15 min | - | 4 ore |
| **SSL Certificate** | 12 ore | - | 24 ore |
| **System updates** | 6 ore | - | 12 ore |

**Politica di alert:** Controlli rilassati con rinotifiche molto spaziate. Questi servizi possono restare offline alcune ore senza impatto critico.

**Razionale:** Servizi importanti per operazioni e manutenzione ma non time-critical. La politica evita alert fuori orario per problemi non urgenti.

### **Dipendenze tra servizi**

**Configurazioni implementate:**

- **MySQL Connection time down** → silenza alert per MAOApi, MAOData, MongoDB
- **Docker Daemon down** → silenza alert per MAOPod service e pods

**Perché:** Quando un servizio base si ferma (come MySQL), si evita di ricevere decine di alert da tutti i servizi che ne dipendono. Così ci si concentra subito sul problema principale invece di perdere tempo a smistare notifiche duplicate.

---

## **Schema Architetturale**

```
┌─────────────────────────────────────────────────────────────────┐
│                    NAGIOS MONITORING SYSTEM                     │
├─────────────────────────────────────────────────────────────────┤
│  🔴 TIER 1 - TRADING CRITICAL (15-30min alerts)                 │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │   MAOApi    │   MAOData   │   MAOPod    │   Fluentd   │      │
│  │   Service   │   Service   │   Service   │   Service   │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
│  ┌─────────────┬─────────────┬─────────────────────────────┐    │
│  │ Docker      │ MAOData     │ MAOPod                      │    │
│  │ Daemon      │ Jobs        │ Pods                        │    │
│  └─────────────┴─────────────┴─────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  🔵 DATABASE SERVICES (30-60min alerts)                         │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │   MySQL     │   MySQL     │   MySQL     │   MongoDB   │      │
│  │ Connection  │ Performance │ Resources   │   maologs   │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
├─────────────────────────────────────────────────────────────────┤
│  🟡 INFRASTRUCTURE (60min-2h alerts)                            │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │  System     │   Network   │   Process   │   Storage   │      │
│  │ Resources   │   Traffic   │  Monitor    │   Monitor   │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
├─────────────────────────────────────────────────────────────────┤
│  🔒 SECURITY & ACCESS (1-4h alerts)                             │
│  ┌─────────────┬─────────────┬─────────────────────────────┐    │
│  │     SSH     │  Fail2ban   │     User Access             │    │
│  │   Service   │   Service   │     Control                 │    │
│  └─────────────┴─────────────┴─────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  🟢 SUPPORT SERVICES (4-24h alerts)                             │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │  MAOAdmin   │   Postfix   │    SSL      │   System    │      │
│  │   Service   │    Mail     │    Cert     │   Updates   │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

---

> **Nota:**  Nel trading ogni minuto di fermo può rappresentare un problema. Per questo ho costruito il monitoring basandomi sull'impatto sul business, non solo su metriche tecniche standard. Se un servizio non critico va down, può aspettare - se si ferma il trading, si interviene subito.