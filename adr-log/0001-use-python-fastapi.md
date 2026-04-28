# Use Python + FastAPI for the backend 

## Context and Problem Statement

The web application needs a backend which takes in API requests and interfaces with the local file system, database storage and language models. The tech stack decided on for the implementation of this backend has considerable impact on future architectural decisions.

## Considered Options

* Python + FastAPI
* Python + Django
* Python + Flask
* NodeJS + ExpressJS

## Decision Outcome

Python + FastAPI. Python is ubiquitous in ML applications and many of the libraries we found for ontology extraction are written in Python. Furthermore, all team members are experienced with the language. Currently, FastAPI is one of the most established Python framework for REST APIs and provides built-in documentation and data validation facilities.

### Consequences

* The use of Python allows us to make use of the language's ML ecosystem
* Since the frontend will invariably be written in JavaScript, the project will use two languages, which may complicate some concerns like data validation, documentation generation or testing.
