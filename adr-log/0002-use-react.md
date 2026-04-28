# Use React for the frontend

## Context and Problem Statement

For the frontend of the web application, a suitable framework can reduce boilerplate and improve code maintainability.

## Considered Options

* Vanilla JS
* React
* Vue
* Svelte

## Decision Outcome

We chose to use React, as all team members had at least some basic familiarity with it. Since React is a library, not a framework proper, it was judged to strike a good balance between simplicity, flexibility and power.

While Svelte was considered as the more sleek and modern option, most of the team members were not familiar with it, and the relatively recent breaking changes in Svelte 5 could cause confusion between the two versions of the framework.

### Consequences

* Many concerns such as state management, tweening, proper stylesheet scoping etc. do not have a built-in React solution and may need further consideration.
