# dagcheck-plan

CI- und Batch-Abhängigkeiten vor der Ausführung prüfen, den kritischen Pfad erklären
und einen Ablauf mit begrenzter Worker-Anzahl simulieren. Das Werkzeug führt keine
Aufgaben aus. Python 3.10+, zur Laufzeit nur Standardbibliothek, MIT-Lizenz.

[English](../README.md) · [简体中文](README.zh-CN.md) · [Русский](README.ru.md)

## Schnellstart

Im Stammverzeichnis des Repositorys:

```sh
python -m pip install .
dagcheck-plan analyze examples/build.json --workers 2 --budget 8
python -m dagcheck_plan analyze examples/build.json --workers 2 --format json
python -m unittest discover -s tests -v
```

Das Beispiel ergibt `fetch -> test -> package`. Sowohl bei unbegrenzter Kapazität
als auch mit zwei Workern beträgt die Dauer 8. Alle Dauern verwenden dieselbe frei
gewählte Einheit, etwa Sekunden oder Minuten.

## Eingabeformat

```json
{"tasks":[{"id":"fetch","duration":2},{"id":"test","duration":5,"needs":["fetch"]}]}
```

Das Wurzelobjekt enthält ausschließlich das Array `tasks`. Jede Aufgabe benötigt
`id` und `duration`; `needs` ist optional und standardmäßig leer. Unbekannte Felder
werden abgewiesen. IDs sind eindeutig, nicht leer, unterscheiden Groß-/Kleinschreibung
und haben keine äußeren Leerzeichen. Maximal 256 Zeichen; Unicode-Kategorie C
(Steuer-, Format-, Surrogat-, private und unbelegte Zeichen) ist ausgeschlossen. Abhängigkeiten müssen vorhandene IDs ohne
Wiederholung sein. Dauern sind endliche, nichtnegative JSON-Zahlen; boolesche Werte
sind ungültig. Leere Graphen und Nulldauern sind erlaubt. Doppelte JSON-Schlüssel,
doppelte/unbekannte Abhängigkeiten, Selbstbezüge und Zyklen erzeugen Fehler.
Zyklusmeldungen zeigen einen tatsächlichen gerichteten Zyklus, nicht bloß blockierte
Nachfolger. Dateien sind UTF-8; `-` liest von der Standardeingabe.

## Ergebnisse und Budget

- `topological_order`: bei jedem Schritt die lexikografisch kleinste verfügbare ID.
- `critical_path`: ein zusammenhängender längster Quell-Senken-Pfad; bei Gleichstand
  die lexikografisch kleinste ID-Folge, nicht die Vereinigung kritischer Knoten.
- `timings`: früheste/späteste Start- und Endzeiten sowie Puffer bei unbegrenzter
  Kapazität. Getrennte Komponenten verwenden das gemeinsame Projektende.
- `unlimited_worker_makespan`: kritische Pfadlänge, eine untere Zeitschranke.
- `worker_lower_bound`: Maximum aus dieser Länge und Gesamtarbeit / Worker-Anzahl.
- `schedule`: nicht unterbrechbare Aufgaben auf identischen Workern. Bereite Aufgaben
  werden nach größter verbleibender kritischer Pfadlänge, dann nach ID priorisiert.
  Alle Abschlüsse zum aktuellen Zeitpunkt werden vor neuen Zuweisungen verarbeitet.
  Aufgaben mit Dauer null enden sofort; ihre Nachfolger können bei der nächsten
  Zuweisung berücksichtigt werden. Die kleinste freie Worker-ID wird zuerst genutzt.
- `heuristic_makespan`: Dauer dieses konkreten zulässigen Plans. Es wird keine globale
  Optimalität behauptet. Budgetüberschreitung beweist keine Unlösbarkeit.

`--workers` ist standardmäßig **1**. `--budget` gilt immer für die simulierte Dauer,
nicht für die untere Schranke. Gleichheit besteht die Prüfung. Ohne Budget ist
`within_budget` JSON null. Exitcodes: **0** gültig und im Budget oder ohne Budget;
**1** gültig, aber dieser Plan überschreitet das Budget; **2** ungültige Eingabe,
Parameter oder nicht lesbare Datei. Berichte gehen an stdout, Fehler an stderr.

Intern werden rationale Zahlen aus der Dezimaldarstellung der bereits eingelesenen
Werte verwendet: 0.1 + 0.2 erfüllt ein Budget von 0.3. Nichtganzzahliges JSON wird
zunächst als Python float eingelesen; beliebige Dezimalpräzision bleibt daher nicht
erhalten. Gebrochene Ausgaben werden auf endliche floats gerundet, ganzzahlige
Ausgaben sind exakt. Budgetvergleiche erfolgen vor der Ausgaberundung.

## Bibliothek

```python
from dagcheck_plan import loads, plan, PlanError
report = plan(loads('{"tasks":[{"id":"lint","duration":3}]}'), workers=2, budget=4)
assert report["within_budget"] is True
```

`plan` akzeptiert ein Dictionary und verändert es nicht. `loads` liest striktes JSON.
Ungültige Daten lösen `PlanError` aus, eine Unterklasse von `ValueError`.
Umordnen der Aufgaben und Abhängigkeiten verändert das Ergebnis nicht.

## Grenzen und Entwicklung

Zeitangaben sind Schätzungen, keine Laufzeitgarantien. Es werden weder Befehle
 ausgeführt noch CI-Geheimnisse gelesen; Startkosten, Caches, Wiederholungen und
Ressourcenklassen werden nicht modelliert. Dies ist kein Optimierer und keine
Sicherheits-Sandbox. Grenzen: 1.000.000 Eingabezeichen, 10.000 Aufgaben, 100.000 Kanten.
Aufgaben-/Kantenlimits gelten auch für die Dictionary-API; rationale Berechnungen können bei
großen Eingaben teuer werden. Nur vertrauenswürdige Projektkonfigurationen verwenden.
NetworkX bietet allgemeine Graphalgorithmen, PyGraphviz eine Graphviz-Anbindung;
dieses Projekt konzentriert sich auf eine CLI-Budgetprüfung ohne Aufgabenausführung.

Tests decken Schema, Zyklen, lange Ketten, Nulldauern, stabile Permutationen,
gleichzeitige Abschlüsse, Budgets, CLI und 100 zufällige DAGs mit festem Seed ab.
CI prüft Python 3.10–3.13 und die installierte CLI. Graphvergleiche, Ressourcenklassen
und ein GitHub-Actions-Adapter sind mögliche Erweiterungen, noch nicht implementiert.
Beiträge benötigen Regressionstests und Aktualisierungen aller vier Sprachfassungen;
siehe [Beitragsleitfaden](../CONTRIBUTING.md). Lizenz: [MIT](../LICENSE).
