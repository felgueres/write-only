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

TODOs
- Add spatial indexing
- Add temporal indexing

-----------------

NOTES while coding

here's what im thinking. i think about creating some analogous thing as RAG for the real world, perhaps
   on satellite data, and starting with camera. i feel that computing a graph first and then asking 
  questions could be very interesting here. 

  so im doing exploratory work to do that. 

  i want to build an ai layer to explore how llms can play a role in the physical world.

CLAUDE
That's a fascinating direction! Building a computational graph from real-world data (satellite
  imagery, camera feeds) before querying it is a brilliant approach. You're essentially creating a
  "scene graph" or "spatial knowledge graph" that an LLM can reason over.

  Some compelling questions this could answer:

  Spatial Reasoning:
  - "What's the relationship between building density and green space coverage?"
  - "Show me areas where urban development is encroaching on natural habitats"
  - "Find regions with similar topological patterns to this reference area"

  Temporal Analysis:
  - "How has this coastline changed over the past 5 years?"
  - "Which agricultural areas show signs of drought stress?"
  - "Track vehicle movement patterns at this intersection"

  Multi-modal Understanding:
  - "What's the correlation between road network density and economic indicators?"
  - "Identify areas suitable for solar installations based on roof orientation and shading"
  - "Find optimal locations for emergency services based on population density and access routes"

  Compositional Queries:
  - "Show me forested areas within 5km of water sources but not near urban development"
  - "Find parking lots that could be converted to green space based on usage patterns"

  The key insight is that by pre-computing the graph (objects, relationships, spatial hierarchies), you
   can ask much more sophisticated questions than just "what do you see in this image?"

  What type of real-world scenario are you thinking of starting with? Urban planning, environmental
  monitoring, infrastructure analysis?

  