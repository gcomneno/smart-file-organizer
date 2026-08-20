# ADR 0002: Contratto di recovery verificabile e modello dei guasti

- Stato: Proposto
- Data: 2026-08-20
- Issue correlate: [#80](https://github.com/gcomneno/smart-file-organizer/issues/80), [#81](https://github.com/gcomneno/smart-file-organizer/issues/81)
- Estende: [ADR 0001](0001-evolution-architecture.md)
- Fonte canonica: [versione inglese](0002-verifiable-recovery-contract.md)

## Contesto

ADR 0001 ha stabilito che la storia registrata nei manifest e lo stato corrente
del filesystem sono concetti distinti, che il recovery deve essere plan-first e
read-only e che gli stati ambigui del filesystem devono essere rappresentati,
non eliminati tramite supposizioni.

Smart File Organizer necessita ora di un contratto di prodotto più rigoroso per
il recovery verificabile.

Il flusso di prodotto di riferimento è:

    Evidence
      -> Plan
        -> Explain
          -> Approve
            -> Apply
              -> Record
                -> Observe
                  -> Verify
                    -> Recover only if safe

L'attuale schema manifest versione 1 registra fatti storici durevoli relativi
all'esecuzione, inclusi path originali e finali e stato di esecuzione dei
movimenti. Non registra hash, fingerprint o evidence equivalente relativa
all'identità del payload.

Un manifest schema v1 può quindi affermare che Smart File Organizer ha
registrato un movimento completato da un path a un altro. Una successiva
osservazione del filesystem può affermare che al path di destinazione esiste
attualmente un file regolare. Nessuno dei due fatti dimostra che la destination
corrente contenga gli stessi byte spostati durante l'apply storico.

Questo ADR definisce la semantica di prodotto e architetturale necessaria prima
che un futuro schema manifest possa aggiungere identity evidence o qualsiasi
capacità di recovery mutante.

Non modifica lo schema manifest versione 1, non aggiunge hashing, non autorizza
l'esecuzione del recovery e non definisce un'interfaccia utente.

## Decisione

### Verifiable trust è il principio guida del recovery

Smart File Organizer non deve richiedere all'utente di fidarsi di una decisione
di rollback ottimistica.

La sicurezza del recovery deve derivare da evidence e osservazioni correnti.
Quando l'evidence disponibile non può dimostrare che il recovery sia sicuro,
l'astensione è il risultato corretto.

La regola normativa è:

> Quando Smart File Organizer non può dimostrare che un'azione di recovery è
> sicura, non deve descriverla come sicura e non deve eseguirla.

Refusal, abstention e risultati unverifiable sono risultati corretti del safety
model. Non sono sostituti degradati di un recovery indovinato.

### Quattro categorie distinte di informazione

Il ragionamento sul recovery deve mantenere separati quattro concetti.

#### Historical fact

Un historical fact è un dato registrato durevolmente relativo a una precedente
operazione di apply.

Esempi:

- versione dello schema manifest;
- target root registrata;
- path sorgente originale;
- path di destinazione finale;
- stato di esecuzione;
- timestamp ed errori di esecuzione registrati.

Gli historical fact descrivono ciò che Smart File Organizer ha registrato sul
passato. Non devono essere riscritti semplicemente perché successivamente il
filesystem cambia.

Un historical fact non dimostra il contenuto corrente o l'identità di un path.

#### Current observation

Una current observation è un'affermazione read-only sullo stato del filesystem
osservato in un determinato momento.

Esempi:

- se il path originale esiste attualmente;
- se la destination esiste attualmente;
- se un oggetto osservato ha un tipo filesystem supportato;
- se un path attraversa attualmente un symlink o un confine di containment
  non sicuro;
- se l'osservazione è fallita o è risultata indeterminata.

Un'osservazione descrive il presente nel momento in cui viene effettuata. Non
riscrive la storia del manifest e non stabilisce da sola l'identità del payload.

#### Identity evidence

Identity evidence è evidence capace di supportare l'affermazione che i byte
osservati adesso corrispondano ai byte registrati in un precedente punto fidato
del workflow.

Un pathname non è identity evidence.

L'esistenza di un file non è identity evidence.

La sola dimensione del file non è identity evidence sufficiente.

Lo schema versione 1 non contiene fingerprint del payload e pertanto non
fornisce una base per la verifica byte-level dell'identità.

Un futuro schema manifest potrà registrare identity evidence, ma algoritmo,
campi, timing, policy di performance e rappresentazione dei symlink sono fuori
dallo scope di questo ADR.

Un futuro fingerprint deve essere descritto in modo ristretto: identifica i byte
osservati secondo la procedura di fingerprinting definita. Non deve essere
descritto come identità filosofica permanente di un documento o file.

#### Recovery-safety decision

Una recovery-safety decision combina historical evidence supportata, fresh
current observations, identity evidence disponibile, controlli di path safety e
controlli di conflitto.

Risponde alla domanda se un'operazione inversa possa essere proposta come
sicura.

Non deve inferire evidence mancante.

Non deve trattare validità del manifest, esistenza dei path o un precedente
risultato di verification come mutation authority.

### Safe recovery

Un reverse move può essere classificato safe to recover solo quando tutte le
precondizioni richieste sono dimostrabilmente soddisfatte.

Come minimo:

1. il manifest storico è valido secondo uno schema supportato;
2. il record storico dimostra che il movimento forward è stato completato;
3. tale schema contiene identity evidence sufficiente per l'identity claim
   supportato;
4. la recovery source corrente può essere osservata nuovamente;
5. la recovery source corrente corrisponde all'identity evidence registrata;
6. il path sorgente originale è attualmente assente e disponibile per il
   ripristino;
7. entrambi i recovery path rispettano la policy corrente di filesystem safety e
   containment;
8. non esiste alcun conflitto di path, alias ambiguity, tipo di file non
   supportato o stato contraddittorio;
9. ogni osservazione necessaria alla decisione è riuscita;
10. la decisione si basa su osservazioni sufficientemente attuali per
    l'operazione che deve essere autorizzata.

Se anche una sola precondizione richiesta non può essere dimostrata, il recovery
deve essere `REFUSED`.

`SAFE_TO_RECOVER` significa che, sulla base dell'evidence e delle osservazioni
correnti, un reverse move può essere proposto come sicuro. Non autorizza una
mutazione del filesystem.

Nessuna combinazione della sola esistenza dei path è sufficiente.

### Verification e recovery safety sono modelli di stato separati

La verification dello stato corrente e l'autorizzazione del recovery rispondono
a domande differenti e non devono essere fuse in un'unica macchina a stati.

La verification deve poter distinguere almeno:

| Verification finding | Significato |
| --- | --- |
| `IDENTITY_MATCH` | L'identità del payload corrente corrisponde a sufficiente evidence registrata. |
| `IDENTITY_MISMATCH` | L'identità del payload corrente contrasta con l'evidence registrata. |
| `SOURCE_OCCUPIED` | Il path sorgente originale è attualmente occupato. |
| `DESTINATION_MISSING` | La recovery source corrente attesa è assente. |
| `BOTH_PRESENT` | Path originale e destination sono entrambi presenti. |
| `BOTH_MISSING` | Path originale e destination sono entrambi assenti. |
| `UNSAFE_PATH` | Un path richiesto viola la policy corrente di filesystem safety. |
| `UNVERIFIABLE` | Identity evidence o osservazioni correnti richieste sono insufficienti. |
| `AMBIGUOUS` | L'evidence disponibile supporta più interpretazioni materialmente differenti. |

Questi sono finding concettuali di verification, non una enum Python
obbligatoria.

La recovery-safety decision ha soltanto due risultati normativi:

| Decisione | Significato |
| --- | --- |
| `SAFE_TO_RECOVER` | Con evidence e osservazioni correnti, un reverse move può essere proposto come sicuro. |
| `REFUSED` | Smart File Organizer non può attualmente dimostrare che il reverse move sia sicuro. |

`REFUSED` non è una categoria di errore. Il suo reason code stabile e i finding
di verification di supporto spiegano se la causa sia contenuto modificato,
conflitto, stato mancante, ambiguity, unverifiability, unsafe path, schema non
supportato o un'altra condizione di sicurezza definita.

Nessuno dei due risultati costituisce mutation authority. `SAFE_TO_RECOVER`
permette una proposta di recovery; qualsiasi futura esecuzione richiede ancora
autorizzazione esplicita e nuove osservazioni safety-critical al mutation
boundary.

### Stable reason codes

Ogni proposta, refusal o abstention di recovery deve esporre uno stable
machine-readable reason code.

Il vocabolario normativo iniziale è:

| Reason code | Significato |
| --- | --- |
| `recovery_preconditions_verified` | Tutta l'evidence e le osservazioni correnti richieste per proporre safe recovery sono soddisfatte. |
| `identity_verified` | L'identità del payload corrente corrisponde a sufficiente evidence registrata; da sola non dimostra recovery safety. |
| `identity_unverifiable` | Lo schema o l'evidence disponibili non possono supportare l'identity claim richiesto. |
| `destination_changed` | Il payload corrente alla destination contrasta con l'identity evidence registrata. |
| `destination_missing` | La recovery source corrente attesa è assente. |
| `source_conflict` | Il path sorgente originale è occupato o comunque indisponibile per il ripristino. |
| `both_paths_present` | Path originale e destination sono entrambi presenti e lo stato non può essere ridotto con sicurezza a una sola interpretazione di recovery. |
| `both_paths_missing` | Nessuno dei due path registrati contiene attualmente l'oggetto atteso. |
| `unsafe_path` | Un path richiesto viola la policy corrente di filesystem safety. |
| `unsupported_file_type` | Un oggetto filesystem richiesto ha un tipo non permesso dal contratto di recovery. |
| `observation_failed` | Un'osservazione filesystem richiesta non ha potuto essere completata in modo affidabile. |
| `manifest_malformed` | Il manifest non può essere validato come historical record supportato. |
| `manifest_schema_unsupported` | La versione dello schema manifest non dispone di reader e semantica esplicitamente supportati. |
| `historical_state_ambiguous` | L'historical execution evidence è insufficiente o contraddittoria per il ragionamento sul recovery. |
| `stale_observation` | Osservazioni precedenti non possono autorizzare con sicurezza una mutation successiva perché lo stato rilevante del filesystem potrebbe essere cambiato. |

Il lavoro futuro può aggiungere reason code quando servono nuove distinzioni
supportate. I significati già pubblicati non devono essere riutilizzati
silenziosamente.

### Human-readable explanations

Ogni risultato di recovery safety deve fornire anche una spiegazione umana
concisa.

La spiegazione deve:

- dichiarare se il recovery è safe o refused;
- spiegare la ragione decisiva senza richiedere la decodifica di una enum;
- distinguere historical facts registrati da current observations;
- evitare claim di byte identity se non supportati da identity evidence;
- evitare leakage del contenuto grezzo dei documenti ispezionati.

Machine-readable reason code e human-readable explanation hanno scopi diversi e
sono entrambi obbligatori.

### Evidence e observations devono rimanere ispezionabili

Una recovery-safety decision deve conservare o esporre abbastanza informazione
strutturata da identificare:

- historical move record rilevante;
- historical field utilizzati;
- identity evidence disponibile;
- current path osservati;
- risultato di ogni osservazione richiesta;
- reason code e recovery-safety decision risultanti.

Il rendering può riassumere queste informazioni, ma gli adapter non devono
inventare claim più forti del decision model sottostante.

### Compatibilità Manifest schema v1

Manifest schema versione 1 rimane un formato storico supportato.

Deve rimanere leggibile secondo il contratto di validazione strict esistente.

Versione 1 registra historical execution evidence utile, ma non contiene payload
hash, fingerprint o identity evidence equivalente. Non deve mai essere
reinterpretato retroattivamente come se tale evidence esistesse.

Di conseguenza un manifest v1 non può, secondo questo ADR, dimostrare byte-level
identity tra un payload storico spostato e un file corrente alla destination.

Il comportamento esistente di verification e recovery planning v1 rimane
comportamento storico del prodotto. Una manual reverse-move proposal v1 basata
sulla path reconciliation non deve essere rinominata come prova di
`SAFE_TO_RECOVER`.

Il lavoro futuro può continuare a esporre inspection v1 prudente o manual
recovery guidance, purché sia esplicito che l'identità è unverifiable.

### Gli schema manifest sconosciuti falliscono closed

Gli schema manifest sono compatibility surface versionate indipendentemente.

Un reader deve comprendere esplicitamente una versione dello schema prima di
utilizzarla per verification o decisioni di recovery safety.

Uno schema futuro sconosciuto deve essere rifiutato come unsupported. Smart File
Organizer non deve:

- supporre che i campi mantengano il significato di v1;
- ignorare identity semantics sconosciute;
- effettuare silent downgrade dello schema;
- inferire recovery authority da campi parzialmente familiari.

Schema semantics sconosciute producono un risultato fail-closed.

Anche manifest malformed non possono conferire recovery authority.

### Threat e failure model

Il recovery model deve gestire in modo conservativo i cambiamenti del filesystem
successivi all'apply.

| Scenario | Interpretazione richiesta |
| --- | --- |
| Destination modificata in-place | Se l'identity evidence non corrisponde più, classificare changed e non toccarla. |
| Destination cancellata | La recovery source è missing; non inventare un reverse move. |
| Destination sostituita da un altro file | Se l'identità differisce o non può essere stabilita, non toccarla. |
| Source originale ricreata | Trattare la posizione originale come occupata; non sovrascriverla mai. |
| Source e destination entrambe presenti | Trattare come conflict o ambiguity salvo che evidence più forte risolva lo stato senza rischiare dati utente. |
| Source e destination entrambe assenti | Trattare come missing; nessuna recovery mutation può essere proposta. |
| Symlink o topologia dei path cambiata | Trattare come unsafe o unverifiable secondo la path-safety policy; non seguire ottimisticamente un trust boundary cambiato. |
| Un'osservazione richiesta fallisce | Trattare come unverifiable o unsafe; failure dell'osservazione non equivale ad assenza. |
| Manifest malformed | Rifiutarlo come historical authority. |
| Manifest schema unsupported | Fallire closed; non indovinarne la semantica. |
| Contenuto destination cambiato ma pathname invariato | La path equality non prevale su una identity verification fallita. |
| Metadata file cambiati ma payload bytes uguali | L'identity judgment dipende esclusivamente dall'evidence esplicitamente definita dallo schema supportato; non inventare identity requirement non documentati. |
| Filesystem cambiato dopo verification | La verification precedente è stale per mutation authorization; le precondizioni richieste devono essere riosservate al mutation boundary. |

### La verification è time-bound

Le osservazioni del filesystem sono fatti relativi a uno specifico evento di
osservazione, non lease sullo stato futuro.

Il filesystem può cambiare dopo la verification e prima del recovery planning o
di una futura recovery execution.

Di conseguenza:

- un risultato di verification non deve concedere mutation authority durevole;
- il recovery planning deve rimanere non-mutating;
- qualsiasi futuro recovery executor deve verificare nuovamente tutte le
  precondizioni safety-critical osservabili immediatamente prima di ogni
  mutation rilevante;
- se lo stato cambia, l'executor deve rifiutare invece di affidarsi a una
  verification stale.

Questo vale anche quando una verification precedente aveva classificato lo
stato come safe.

### Mutation authority rimane esplicita e appartiene a lavoro futuro

Questo ADR non autorizza alcuna recovery mutation.

Una futura implementazione della recovery execution, se approvata
separatamente, deve mantenere i principi esistenti del progetto:

- autorizzazione esplicita dell'utente;
- nessun silent overwrite;
- path safety fail-closed;
- current precondition check;
- failure reporting veritiero;
- durable evidence;
- nessuna inferenza di authority da uno stage precedente riuscito.

La capacità di verificare un payload non autorizza di per sé a spostarlo.

La capacità di pianificare un recovery non autorizza di per sé a eseguirlo.

### Implicazioni per un futuro schema manifest

Un futuro schema manifest progettato per verifiable recovery deve fornire
evidence sufficiente a supportare l'identity claim richiesto da questo ADR.

Quel futuro design dovrà decidere separatamente:

- rappresentazione del cryptographic fingerprint;
- eventuali size o metadata identity-related di accompagnamento;
- momento del fingerprinting;
- semantica pre-move e post-move;
- semantica dei symlink;
- rappresentazione della schema version;
- compatibilità con v1;
- costo del fingerprinting e performance policy.

Queste sono domande progettuali della issue Manifest v2, non decisioni prese
qui.

Qualunque rappresentazione venga scelta deve mantenere la regola semantica per
cui un fingerprint identifica i byte osservati secondo la procedura definita e
non rappresenta un'identità permanente del documento.

## Invarianti preservati

Questo ADR non indebolisce gli invarianti accettati da ADR 0001 o dal contratto
corrente del repository:

- dry run di default;
- apply esplicito;
- comportamento e output deterministici dove specificato;
- nessun silent overwrite;
- target-root containment;
- failure-aware execution;
- durable recovery evidence;
- diagnostica controllata;
- ambiguity e abstention;
- explanation privacy-safe;
- continua leggibilità di Manifest schema versione 1;
- fail-closed per schema manifest unsupported;
- verification e recovery planning non mutanti.

## Conseguenze

Il beneficio principale è rendere auditabili i claim di recovery.

Smart File Organizer può distinguere:

1. ciò che ha registrato storicamente;
2. ciò che osserva adesso;
3. ciò che l'identity evidence supporta;
4. quale recovery action è dimostrabilmente sicura.

Il costo principale è l'astensione deliberata.

Alcuni manifest storici, in particolare schema v1, non possono supportare una
classificazione positiva di safe recovery perché privi di identity evidence.
Questa limitazione è comportamento di prodotto veritiero, non una ragione per
indebolire il contratto.

Future API, CLI e user interface devono proiettare questo trust model invece di
inventare semantiche alternative di recovery.

## Non-goal

Questo ADR non:

- definisce i campi Manifest v2;
- seleziona un algoritmo hash;
- implementa fingerprinting;
- modifica la serializzazione manifest;
- cambia il parsing schema v1;
- implementa recovery execution;
- aggiunge automatic rollback;
- aggiunge `recover --apply`;
- costruisce o prototipa una GUI;
- promette filesystem-wide atomicity;
- autorizza overwrite;
- trasforma la path reconciliation v1 in identity verification.

## Alternative rifiutate

### Trattare l'esistenza della destination come identità

Rifiutato perché un altro payload può occupare lo stesso pathname dopo
l'apply storico.

### Trattare le recovery proposal schema v1 come prova di safe recovery

Rifiutato perché schema v1 non contiene identity evidence capace di dimostrare
che la destination corrente contenga ancora il payload storico.

### Recovery ottimistico con warning

Rifiutato perché un warning non impedisce una mutation distruttiva quando
identity o conflict state sono incerti.

### Indovinare la semantica di schema sconosciuti

Rifiutato perché campi e identity guarantee possono cambiare tra versioni.
Gli schema unsupported devono fallire closed.

### Verification come mutation authority durevole

Rifiutato perché lo stato del filesystem può cambiare dopo l'osservazione.
Lo stato safety-critical deve essere rivalutato al futuro mutation boundary.

### Automatic unconditional undo

Rifiutato perché confligge con evidence-based recovery, no-overwrite guarantee,
gestione dell'ambiguity e governance rule della issue #80.

## Governance

Issue #80 stabilisce la seguente regola:

> No child issue may introduce an automatic recovery mutation until identity
> verification and recovery-safety classification have survived at least one
> released version.

Questo ADR preserva tale regola.

Nessuna implementazione derivata da questo ADR può utilizzare la capacità di
verification come scorciatoia per aggirarla.
