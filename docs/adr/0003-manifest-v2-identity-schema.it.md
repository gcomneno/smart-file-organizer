# ADR 0003: Schema di identità e fingerprint di Manifest v2

- Stato: Accettato
- Data: 2026-08-23
- Issue correlate: [#80](https://github.com/gcomneno/smart-file-organizer/issues/80), [#85](https://github.com/gcomneno/smart-file-organizer/issues/85)
- Dipende da: [ADR 0002](0002-verifiable-recovery-contract.it.md)
- Fonte canonica: [versione inglese](0003-manifest-v2-identity-schema.md)

## Contesto

ADR 0002 definisce il contratto normativo di recovery per Smart File Organizer.
Historical fact, current filesystem observation, payload identity evidence e
recovery-safety decision sono concetti distinti. Un'azione di recovery può essere
classificata `SAFE_TO_RECOVER` soltanto quando identity evidence sufficiente e
osservazioni correnti del filesystem dimostrano le precondizioni di sicurezza
richieste.

Manifest schema versione 1 registra una storia durevole dell'esecuzione ma non
registra payload identity evidence. Rimane quindi utile per ispezione storica e
path reconciliation, ma non può dimostrare che i byte presenti oggi alla
destination registrata siano quelli spostati dall'apply storico.

Issue #85 richiede un contratto persistito di identity evidence capace di
supportare la futura current-state verification senza modificare il comportamento
di apply in questa issue.

L'executor esistente usa `shutil.move()`. Sullo stesso filesystem questo
normalmente si riduce a una rename, mentre tra filesystem diversi può effettuare
una copy seguita dalla rimozione della sorgente. Un fingerprint acquisito solo
prima del move dimostrerebbe quindi quali byte della sorgente sono stati
osservati, ma da solo non dimostrerebbe quali byte siano presenti alla destination
finale dopo il move.

Questo ADR definisce Manifest v2 con precisione sufficiente per una successiva
issue sul writer. Non implementa hashing, serializzazione, current-state
verification, recovery-safety classification, recovery execution o GUI.

## Decisione

### Manifest v2 è un contratto persistito versionato indipendentemente

Manifest v2 usa il campo top-level esistente `schema_version` con valore intero
`2`.

Le versioni del package e le versioni dello schema manifest rimangono superfici
di compatibilità indipendenti. Una release del package può continuare a leggere
più di uno schema manifest. Un cambio di versione del package non implica un
cambio dello schema manifest e un cambio dello schema manifest non deve essere
inferito dalla versione del package.

I reader devono effettuare dispatch esplicito tramite `schema_version`.

- `schema_version == 1` viene interpretato solo secondo il contratto strict v1
  esistente.
- `schema_version == 2` viene interpretato solo secondo il contratto v2 definito
  qui.
- qualsiasi altro valore è unsupported finché non viene implementato
  deliberatamente un reader per quella versione esatta.

Le versioni non supportate falliscono closed con la semantica
`manifest_schema_unsupported` già stabilita. I reader non devono presumere che
campi familiari mantengano lo stesso significato in uno schema sconosciuto.

All'interno di v2 lo schema è strict. Campi top-level sconosciuti, campi move
sconosciuti, campi identity-evidence sconosciuti, chiavi JSON duplicate, campi
obbligatori mancanti e combinazioni contraddittorie sono errori di validazione.
L'estensibilità viene fornita da una successiva versione esplicita dello schema,
non accettando silenziosamente dati dalla semantica sconosciuta.

### v2 preserva la forma della execution history v1 e aggiunge identity evidence

Manifest v2 preserva i campi top-level di execution history già stabiliti:

```text
schema_version
state
target_root
started_at
updated_at
finished_at
counts
moves
```

Ogni move preserva i campi storici già esistenti:

```text
original_path
final_path
category
status
timestamp
error
```

e aggiunge esattamente un nuovo campo:

```text
identity
```

`identity` è `null` oppure un oggetto strutturato contenente identity evidence
sufficiente per il move storico completato.

L'oggetto identity iniziale di v2 è:

```json
{
  "algorithm": "sha256",
  "digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "size_bytes": 12345,
  "source_observed_at": "2026-08-23T07:30:00+00:00",
  "destination_observed_at": "2026-08-23T07:30:01+00:00"
}
```

L'oggetto identity descrive una successful two-sided payload observation. Significa
che:

1. i byte del regular file sorgente sono stati osservati prima del move;
2. quei byte hanno prodotto il digest SHA-256 e il byte count registrati;
3. dopo il ritorno dell'operazione di move e il successo delle postcondition
   esistenti, i byte del regular file di destination sono stati osservati;
4. la destination ha prodotto lo stesso digest SHA-256 e lo stesso byte count;
5. le osservazioni source e destination supportano quindi l'historical claim che
   il move completato abbia trasferito i byte del payload osservato.

L'oggetto identity **non** significa che la destination conserverà quei byte per
sempre. È historical evidence acquisita durante apply. Qualsiasi identity claim
successivo richiede una nuova current observation e un confronto.

### SHA-256 è l'algoritmo di fingerprint iniziale

L'identifier dell'algoritmo v2 è la stringa ASCII lowercase stabile:

```text
sha256
```

Il digest è codificato esattamente come 64 caratteri esadecimali lowercase.

L'algoritmo viene registrato per ogni identity object anche se schema v2 consente
inizialmente soltanto `sha256`. Registrarlo evita semantiche implicite e fornisce
un confine di migrazione esplicito per schemi futuri.

Un reader v2 deve rifiutare un identity object il cui `algorithm` non sia
`sha256`. Non deve tentare interpretazioni best-effort, alias resolution,
sostituzioni dell'algoritmo o downgrade.

SHA-256 viene scelto perché è un hash crittografico standard, disponibile nella
standard library Python, non richiede servizi di rete o dipendenze runtime
aggiuntive e fornisce un fingerprint byte-level sufficientemente forte per
questo contratto di prodotto.

Il fingerprint non è una digital signature e non autentica chi abbia creato il
manifest.

### Identity evidence richiede osservazioni sia pre-move sia post-move

Un identity record v2 riuscito richiede due osservazioni complete.

#### Source observation

Immediatamente prima del consequential move di un item, il writer deve osservare
la sorgente come supported regular file e calcolare:

- SHA-256 sull'intero byte stream;
- `size_bytes` esatto sullo stesso byte stream osservato;
- `source_observed_at` dopo il completamento riuscito dell'osservazione.

Il timestamp rappresenta il completamento dell'osservazione. Non è un filesystem
mtime e non deve essere derivato dai metadata del file.

#### Destination observation

Dopo il ritorno dell'operazione di move e il successo delle minimum postcondition
esistenti, il writer deve osservare la destination finale come supported regular
file e calcolare gli stessi valori:

- SHA-256 sull'intero byte stream della destination;
- byte count esatto sullo stesso stream;
- `destination_observed_at` dopo il completamento riuscito dell'osservazione.

Digest e size della destination devono essere uguali a digest e size della
sorgente prima che il move possa essere registrato come `COMPLETED` con identity
evidence non-null.

Questa regola two-sided è necessaria perché i move cross-filesystem possono
comportare copy e delete anziché una rename atomica. L'osservazione post-move
verifica i byte effettivamente arrivati alla destination finale secondo la
procedura di apply supportata.

### Un move v2 `COMPLETED` deve contenere identity evidence completa

Per schema v2, un move con status `completed` deve avere un oggetto `identity`
non-null e valido.

Un move non deve essere registrato `completed` in v2 soltanto perché la
transizione di pathname è riuscita. La completion secondo il contratto writer v2
include acquisizione riuscita della payload evidence e uguaglianza tra i
fingerprint source e destination.

Per gli status `in_progress`, `failed` e `unattempted`, `identity` deve essere
`null`.

Questo mantiene deliberatamente il primo contratto persistito v2 binario e
auditabile: l'identity evidence è sufficientemente completa da supportare la
successiva byte-level verification oppure è assente. v2 non pubblica partial
identity object con forza probatoria ambigua.

Un'implementazione può mantenere temporaneamente in memoria il fingerprint
pre-move mentre un item è in progress, ma non deve serializzare quella
osservazione temporanea come completed identity evidence.

### Un fallimento del fingerprinting è un apply failure per quel move

Se la source observation richiesta fallisce, il move non deve essere tentato.
L'item diventa `failed` secondo il failure-aware execution model esistente e
`identity` rimane `null`.

Se il filesystem object non è più un supported regular file al required
observation boundary, il move deve fail closed.

Se il move stesso fallisce, l'item rimane `failed` e `identity` resta `null`, a
prescindere da eventuale fingerprint temporaneo della sorgente già calcolato.

Se la destination observation fallisce dopo che la pathname mutation è avvenuta,
l'item deve essere registrato `failed` con `identity: null`. Il failure record
deve riportare in modo veritiero che il contratto di completion v2 non è stato
stabilito. I meccanismi esistenti di manifest e filesystem reconciliation restano
responsabili di rappresentare lo stato parziale risultante; il writer non deve
ridenominarlo completed soltanto perché esiste una destination path.

Se source e destination digest o size differiscono, l'item deve analogamente
essere registrato `failed` con `identity: null`. Un mismatch è un safety failure,
non un successful move con warning.

I move pianificati successivi restano unattempted secondo il contratto esistente
stop-at-first-failure.

### v2 non afferma di eliminare tutte le finestre TOCTOU

La two-sided observation rafforza materialmente l'historical claim, ma non rende
il filesystem transactional.

Un file può cambiare mentre viene letto per il fingerprinting o tra le
osservazioni perché Smart File Organizer non applica lock esclusivi arbitrari ai
file utente. Il contratto v2 afferma quindi soltanto ciò che è stato osservato
secondo la procedura definita.

Il writer non deve affermare che la sorgente sia rimasta immutabile durante
l'intera operazione.

Come minimo, l'issue di implementazione deve garantire che ciascun digest e size
siano calcolati dallo stesso file stream aperto e rappresentino i byte consumati
da quell'osservazione. Se il sistema operativo segnala un read error o un'altra
condizione che impedisce un'osservazione completa, l'osservazione fallisce.

Il verifier successivo deve comunque effettuare una fresh observation del
payload corrente della recovery source. Un historical v2 identity object non
diventa mai durable mutation authority.

Qualsiasi futuro recovery executor deve riosservare tutte le precondizioni
filesystem safety-critical al mutation boundary come richiesto da ADR 0002.

### Identity evidence e convenience metadata rimangono distinti

Solo i seguenti campi v2 partecipano al payload-identity matching:

- `algorithm`;
- `digest`;
- `size_bytes`.

`source_observed_at` e `destination_observed_at` sono historical observation
metadata. Stabiliscono quando l'evidence è stata acquisita ma non rafforzano né
indeboliscono la byte equality.

Path, filename, category, timestamp, filesystem mtime, inode number, device
number, ownership, permission e path existence non sono payload identity
evidence in v2.

In particolare:

- pathname uguali non stabiliscono identity;
- size uguali senza digest corrispondente non stabiliscono identity;
- mtime uguali non stabiliscono identity;
- metadata inode/device uguali non sono richiesti per identity e non devono
  essere persistiti come identity requirement;
- metadata modificati con byte invariati non implicano da soli identity mismatch.

### Confine regular-file

Il contratto identity iniziale v2 si applica soltanto ai payload supported regular
file.

Un symlink non viene fingerprintato dereferenziandolo come se i byte del target
fossero il payload del symlink. Directory, device node, FIFO, socket e altri
special filesystem object sono fuori dal contratto identity v2.

La source/path-safety policy esistente resta autoritativa. Se un path richiesto
risolve a un object non supportato o viola il safety boundary attivo, il writer
deve fail closed anziché fabbricare identity evidence.

Questo ADR non amplia l'insieme di filesystem object che Smart File Organizer può
spostare.

### Contratto canonico dei campi v2

I campi top-level v2 hanno gli stessi significati e constraint di validazione di
v1 salvo dove questo ADR stabilisce diversamente.

Il contratto move-level è:

| Campo | Contratto v2 |
| --- | --- |
| `original_path` | Canonical absolute historical source path secondo il path contract esistente. |
| `final_path` | Canonical absolute destination path; deve rispettare la relazione target-root esistente. |
| `category` | Valore file-category stabile esistente. |
| `status` | Execution status esistente. |
| `timestamp` | Semantica esistente del move-status timestamp. |
| `error` | Semantica esistente dell'error object; richiesto solo per `failed`. |
| `identity` | Identity object completo solo per `completed`; `null` altrimenti. |

Il contratto identity-level è:

| Campo | Contratto v2 |
| --- | --- |
| `algorithm` | Esattamente `sha256`. |
| `digest` | Esattamente 64 caratteri esadecimali lowercase. |
| `size_bytes` | JSON integer non negativo; i boolean non sono validi. |
| `source_observed_at` | Timestamp ISO-8601 timezone-aware entro l'execution interval del manifest. |
| `destination_observed_at` | Timestamp ISO-8601 timezone-aware non precedente a `source_observed_at` ed entro l'execution interval. |

Per un completed move, il `timestamp` esistente rappresenta il completamento
dell'intero contratto di esecuzione v2 e quindi non deve essere precedente a
`destination_observed_at`.

### Regole di consistenza manifest-level

Un manifest v2 è malformed se si verifica una delle seguenti condizioni:

- il suo field set non è esattamente quello supportato da v2;
- `schema_version` non è esattamente `2`;
- falliscono gli invarianti v1 esistenti su state/count/timestamp/path;
- un move `completed` ha `identity: null`;
- un move non-completed ha identity data non-null;
- un identity object contiene campi sconosciuti o mancanti;
- `algorithm` non è `sha256`;
- `digest` non è canonical lowercase SHA-256 hex esatto;
- `size_bytes` è negativo, non-integer o boolean;
- un observation timestamp è mancante, naive, fuori dall'execution interval o
  ordinato in modo errato;
- il move completion timestamp precede la destination observation;
- il destination path viola la relazione target-root safety esistente;
- combinazioni error/status contraddicono l'execution model esistente.

Il reader valida la struttura persistita e la consistenza storica. Non ricalcola
gli hash storici durante il parsing del manifest.

### Esempio rappresentativo di manifest v2

L'esempio seguente è esplicativo e illustra il contratto normativo dei campi:

```json
{
  "schema_version": 2,
  "state": "completed",
  "target_root": "/home/example/organized",
  "started_at": "2026-08-23T07:30:00+00:00",
  "updated_at": "2026-08-23T07:30:01+00:00",
  "finished_at": "2026-08-23T07:30:01+00:00",
  "counts": {
    "completed": 1,
    "failed": 0,
    "in_progress": 0,
    "unattempted": 0
  },
  "moves": [
    {
      "original_path": "/home/example/inbox/report.pdf",
      "final_path": "/home/example/organized/documents/report.pdf",
      "category": "documents",
      "status": "completed",
      "timestamp": "2026-08-23T07:30:01+00:00",
      "error": null,
      "identity": {
        "algorithm": "sha256",
        "digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "size_bytes": 12345,
        "source_observed_at": "2026-08-23T07:30:00+00:00",
        "destination_observed_at": "2026-08-23T07:30:01+00:00"
      }
    }
  ]
}
```

### La compatibilità v1 è preservata senza evidence retroattiva

Manifest v1 rimane leggibile dal reader v1 secondo lo schema esatto e le regole
di validazione già esistenti.

Un move v1 non acquisisce mai un `identity` object per inferenza.

Reader, migration command, verifier o recovery planner non devono hashare una
current v1 destination e presentare quel risultato come identity evidence
acquisita dall'historical apply. Un simile hash sarebbe una current observation,
non un historical fact.

Quando una futura identity verification richiede historical payload evidence, un
record v1 produce la semantica ADR 0002 `identity_unverifiable` anziché un positive
identity result indovinato.

Non esiste alcuna procedura di historical upgrade in-place v1-to-v2 secondo
questo ADR.

### L'autenticità del manifest è fuori da v2

Manifest v2 non aggiunge checksum del manifest, MAC o digital signature.

Il manifest viene trattato come local historical evidence persistita nello stesso
storage trust boundary di v1. L'identity hash risponde alla domanda se i payload
bytes osservati corrispondano ai payload bytes registrati; non dimostra che il
manifest stesso sia stato scritto da Smart File Organizer o non sia stato
modificato da un attore con write access al manifest.

Aggiungere manifest authenticity richiederebbe threat model, key/trust-anchor
design, rotation/recovery policy e user-facing verification contract separati. È
intenzionalmente fuori dal requisito di prodotto corrente e non deve essere
implicato dalla parola "verifiable".

Un manifest malformed o internamente contraddittorio continua a fail closed.

### Implicazioni privacy

v2 non memorizza file content né extracted document text.

I digest SHA-256 sono one-way fingerprint anziché plaintext, ma non sono
privacy-neutral. Una parte che possiede già o può indovinare candidate content
può hashare quel contenuto e confrontare il risultato. I manifest rimangono
quindi metadata potenzialmente sensibili e devono essere protetti con la stessa
cura dei path storici che già contengono.

Nessun network service è richiesto o consentito per il fingerprinting v2.

### Implicazioni performance

Un completed move v2 richiede di leggere l'intero payload due volte: una alla
sorgente e una alla destination.

La scelta è deliberata. Il prodotto privilegia un historical transfer claim più
forte rispetto a un fingerprint solo pre-move meno costoso ma incompleto.

L'issue di implementazione può usare bounded-memory streaming e una chunk size
appropriata, ma non deve indebolire il contratto campionando solo parte del file,
saltando la post-move observation o disabilitando silenziosamente l'hashing oltre
una size threshold.

Se il fingerprint completo non può essere eseguito, il move non può soddisfare la
semantica di completion v2.

Ottimizzazioni di performance basate su evidenza misurata possono essere proposte
separatamente, purché preservino garanzie identity equivalenti.

## Failure e threat model

| Scenario | Interpretazione v2 richiesta |
| --- | --- |
| Source unreadable prima del move | Fail del move; nessuna mutazione; `identity: null`. |
| Source cambia durante fingerprinting | L'hash rappresenta i byte letti da quell'osservazione; read failure abortisce. Il contratto non afferma exclusive immutability. |
| Source cambia dopo la pre-move observation ma prima del move | Il post-move mismatch causa failure; nessuna completed identity evidence viene pubblicata. |
| Same-filesystem rename | Il post-move fingerprint rimane obbligatorio per il contratto di completion v2. |
| Cross-filesystem copy/delete move | Post-move fingerprint obbligatorio; source e destination fingerprint/size devono coincidere. |
| Move operation fallisce | Registra la semantica failure esistente; `identity: null`. |
| Destination unreadable dopo il move | Registra failed v2 completion; `identity: null`; preserva truthful partial-state evidence. |
| Destination hash differisce | Registra failed v2 completion; mai downgrade a warning. |
| Destination modificata o sostituita successivamente | Historical v2 identity resta invariata; il verifier successivo restituisce mismatch se la current evidence differisce. |
| Destination eliminata successivamente | Historical v2 identity resta invariata; la current observation riporta missing state. |
| Original source ricreata | Historical identity non autorizza overwrite; la successiva recovery safety deve rifiutare il conflitto. |
| Unsupported algorithm in presunti dati v2 | Manifest malformed/unsupported per identity use; fail closed. |
| Malformed digest o identity fields contraddittori | Manifest malformed; fail closed. |
| Symlink o special file all'observation boundary | Unsupported/unsafe; fail closed. |
| Payload molto grande | Full streaming fingerprint ancora richiesto; nessun silent sampling o size-based bypass. |
| Manifest modificato dopo apply | v2 non fornisce authenticity guarantee; la validazione interna può rilevare contraddizioni ma una modifica apparentemente valida è fuori da questo threat contract. |

## Conseguenze

Il beneficio principale è che un completed move v2 contiene historical identity
evidence sufficiente affinché un futuro verifier possa confrontare i current
destination bytes con i byte osservati durante l'apply originale.

La two-sided observation attribuisce inoltre al record storico un significato più
forte sia nei move rename-style sia nei move copy/delete-style.

Il costo è I/O aggiuntivo e una definizione più rigorosa di successful apply. Un
move la cui pathname mutation sia riuscita ma il cui post-move fingerprint non
possa essere stabilito è un failed v2 apply item, perché il prodotto non può
affermare verifiable completion in modo veritiero.

Questo comportamento più rigoroso è intenzionale e compatibile con il principio
di ADR 0002: evidence mancante non deve essere promossa a trust.

## Vincoli di implementazione per la prossima issue

La issue del Manifest v2 writer deve preservare questi confini:

- nessun cambio al significato o alla leggibilità dei manifest v1 esistenti;
- nessun hashing durante dry-run planning;
- fingerprint soltanto come parte di explicit apply;
- complete streaming SHA-256 e byte counting;
- source observation immediatamente prima di ogni consequential move;
- destination observation dopo le move postcondition;
- uguaglianza richiesta prima di persistere `COMPLETED`;
- `identity: null` per ogni record non-completed;
- atomic durable manifest update ancora presente;
- stop-at-first-failure ancora presente;
- nessun current-state verifier o recovery-safety classifier nascosto nel writer;
- nessun `recover --apply` o automatic rollback.

L'implementazione può rifinire private type e helper name, ma non deve cambiare
queste semantiche persistite senza una nuova architecture decision.

## Invarianti preservati

Questo ADR preserva:

- dry run by default;
- explicit apply;
- deterministic persisted representation;
- no silent overwrite;
- target-root containment;
- failure-aware execution;
- durable recovery evidence;
- controlled diagnostics;
- privacy-safe explanations;
- strict v1 readability;
- fail-closed handling degli unknown schema;
- abstention quando l'evidence è insufficiente;
- nessuna recovery mutation authority derivata dalla sola historical evidence.

## Non-goal

Questo ADR non:

- implementa il Manifest v2 writer;
- calcola hash in production code;
- cambia il current apply behavior;
- cambia serializzazione o validazione v1;
- definisce l'implementazione della current-state identity verification;
- implementa recovery-safety classification;
- cambia recovery planning;
- definisce recovery execution;
- aggiunge automatic rollback;
- aggiunge `recover --apply`;
- aggiunge una GUI;
- aggiunge manifest signing o authenticity guarantee;
- aggiunge remote storage, network service o external hashing service.

## Alternative rifiutate

### Fingerprint solo pre-move

Rifiutato perché dimostra quali source bytes sono stati osservati ma non quali
byte siano arrivati alla destination finale, soprattutto quando il move attraversa
filesystem e diventa copy/delete.

### Fingerprint solo post-move

Rifiutato perché registra i destination bytes dopo l'operazione ma non li lega
indipendentemente ai byte osservati alla sorgente immediatamente prima del move.

### File size più metadata invece di un hash crittografico

Rifiutato perché size, mtime, inode, device number e path metadata non forniscono
la byte-level identity evidence richiesta.

### Hashing opzionale soltanto per file piccoli

Rifiutato perché lo stesso stato `COMPLETED` avrebbe garanzie identity differenti
in base alla file size. v2 richiede un unico contratto semantico auditabile.

### Hashing parziale/campionato

Rifiutato perché il sampling indebolisce l'identity claim e crea inutile ambiguità
algoritmica nello schema iniziale.

### Persistenza di partial pre-move evidence sui failed record

Rifiutata per v2 perché introdurrebbe molteplici evidence-strength state prima
che verifier e recovery classifier esistano. Il primo contratto v2 mantiene la
published identity evidence completa oppure assente.

### Trattare SHA-256 come manifest authenticity

Rifiutato perché un payload digest non autentica il manifest né il suo autore.
L'authenticity richiede threat e key-management model separati.

## Follow-up

Dopo l'accettazione di questo ADR, la prossima issue focalizzata deve implementare
la scrittura di Manifest v2 durante explicit apply, preservando la leggibilità di
v1 e il failure-aware execution model esistente.
