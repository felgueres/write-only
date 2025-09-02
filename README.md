=====================
=   knowledge tree  = 
=====================

Why do it?
* How does Knowledge Graphs work
* Help understand concepts better
* Personal recommendation system
* Make a map of what I know 
* Similar to a tech tree, you unlock new nodes over time 

What should it do?
* Find relationships between books and ideas
* Build a timeseries of events 
* Recommend and compare to wikipages
* LLM legible context for my queries 

KG -> (Subject, Predicate, Object) 
* Subjects are Entities
* Predicate are relations, edges in the graph
* Object are either another entity or node or a literal value, eg. dates

Classes / Types
* Book
* Highlight
* Entity (people, orgs, places, things)
* Concept

Predicates: connects resources
* inBook (Highlight -> Book)
* mentionsEntity (Highlight -> Entity)
* refersToConcept (Highlight -> Concept)

Ontology
* Defines which classes exist and how they relate
* Defines classes or types, properties or predicates, and constraints like inBook has domain Highlight and range Book
* KG is the instances following those definitions

Setup
- pip3 install spacy
- python3 -m spacy download en_core_web_sm

Graph
* JSON-LD (https://www.w3.org/TR/json-ld/)
* Context JSON-LD tells the processor how to expand short term into full IRIs and how to interpret them

System design
Data ingestion > Entity & Concept Extraction > Disambiguation > Apply Ontology > Triple Extraction > Confidence Scoring (supported by multiple sources, primary, secondary, of what kind) (for already structured data import direclty from source like Wikipedia infobox) > Graph storage > Indexing > Query-time matching with entities and predicates > Pull entity description, get top properties and rank by salience to query, enrich with other meta like images, related entities > User Feedback & Refinement

Why now?
- before: rule-based, stat models, human curation
- now: supervised relation-extraction models (transformers fine-tuned on datasets like TACRED, FewRel, DocRED)

What to support next?
- What are the facts about X that are relavant for search query Y?
- What are related entities to X?

USAGE
> python3 ./generator.py
> python3 ./report.py read_graph.jsonld --plot kg:entity/america
