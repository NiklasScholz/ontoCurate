# Usage of Redis and Celery as an Asynchronous Task Queue

## Context and Problem Statement
The extraction pipeline (in particular ontoGPT) takes a long time to finish (up to over an hour for very large documents).
Running these synchronously inside FastAPI would directly block the HTTP connection for the entire duration, making it unresponsive and prevents parallel task execution. 
Therefore, an asynchronous task system is required that allows:
- The user to not have to wait for the API request to finish (i.e., tasks run in the background)
- Can execute linking or lookup tasks while extracting other runs
- Allows for waiting in case of reached rate limits

## Considered Options

### Option 1: FastAPI BackgroundTasks

FastAPI provides a built-in `BackgroundTasks` mechanism that runs a function after the response is returned, within the same process.

| Pros | Cons                             |
|------|----------------------------------|
| No additional dependency | No retry logic                   |
| Zero configuration | Unreliable                       |
| | Fully attached to FastAPI server |

### Option 2: Celery + RabbitMQ

Celery with RabbitMQ as the message broker. Tasks are pushed to RabbitMQ and picked up by Celery workers.

| Pros                                                    | Cons                            |
|---------------------------------------------------------|---------------------------------|
| Most standard together with Celery                      | Requires another db for results |
| Reliable                                                | Higher overhead than redis      |
| Suited for high traffic                                 |   Workers make code more complex      |
| Retry Logic                                             |  |


### Option 3: Celery + Redis (chosen)

Celery with Redis as both the message broker and the result backend

| Pros                                                    | Cons                           |
|---------------------------------------------------------|--------------------------------|
| Only one additional service                             | Workers make code more complex |
| Retry logic, rate limiting and error handling           |                                |
| Scalable                                                |                                |

## Decision Outcome
**Option 3: Celery + Redis** is chosen based on its advanced retry logic, possibility to take care of rate limiting and error handling, while keeping additional services used rather low.

## Consequences

### Positive Consequences
- No blockage of FastAPI and client can do other things while workers are running
- Parallel execution of tasks is possible
- Automatic Queue Handling (i.e., waiting for other tasks to finish) by Celery

### Negative Consequences
- Workers need to be initialized correctly with API tokens and environment to execute ontoGPT in
- Pipeline dependant on uptime of Redis + Celery $\rightarrow$ crashes not as easy to detect as for FastAPI crashes
### Neutral Consequences
- Task ids need to be stored along pipeline id to be able to poll the status per document/per task for the frontend
