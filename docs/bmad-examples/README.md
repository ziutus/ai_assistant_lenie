
## Kolejność plików do przejrzenia
- [PRD_example_clean.txt](clean/PRD_example_clean.txt) - PRD dla przejścia z RAW SQL queries to ORM, alchemy itp. (zwróć uwagę na linię 454 i 'brak wymogów regulacyjnych')
- [PRD_example_2_clean.txt](clean/PRD_example_2_clean.txt) - 50 metod na pogłębienie zrozumienia zagadnienia, 
- [PRD_example_epics_clean.txt](clean/PRD_example_epics_clean.txt) - epic review
- [PRD_validation_clean.txt](clean/PRD_validation_clean.txt) - da się przetestować? czy wymagania funkcjonalne spełniają wymagania kryteriów SMART?
- [PRD_arch_clean.txt](clean/PRD_arch_clean.txt) - tworzenie architektury na podstawie PRD, zwróć uwagę na linie 437: PRD mówi o eliminacji StalkerWebDocumentDB, ale plan migracji proponuje thin 
  wrapper delegujący do ORM modelu (z __getattr__/__setattr__).) zwróć też uwagę na linie 524: pytanie o Pydantic.
- [PRD_to_EPICS_clean.txt](clean/PRD_to_EPICS_clean.txt)
- [epics_to_stories_clean.txt](clean/epics_to_stories_clean.txt) - tworzymy stories 

Jeżeli w którymś momencie się zgubisz, możesz poprosić o pomoc: [PRD_help_co_dalej_1_clean.txt](clean/PRD_help_co_dalej_1_clean.txt)

## Jeżeli was to zainteresowało

* https://github.com/bmad-code-org/BMAD-METHOD 
* https://docs.bmad-method.org/
* https://docs.bmad-method.org/reference/workflow-map/ - workflow
* https://docs.bmad-method.org/reference/agents/ - agents
