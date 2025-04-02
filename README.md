# Character-Based Delphi Method for the Dragon's Teeth Dilemma

This project uses local LLM models to simulate a multi-agent Delphi method approach to solving an ethical dilemma inspired by Star Trek. The agents take on the personas of various cartoon characters to provide diverse perspectives on a central ethical question:

> **Should we revive an ancient civilization of powerful warriors who have been in suspended animation for 900 years, considering the potential consequences to the balance of power in the region?**

## Quick Start: Reading Character Responses

To dive right into the character perspectives, check the `delphi_round1/` directory after running the simulation. Each character's ethical analysis is available as both a JSON file and a readable Markdown file:

- `delphi_round1/bugs-bunny.md` - The laid-back pragmatist's view
- `delphi_round1/lisa-simpson.md` - The analytical child prodigy's perspective
- `delphi_round1/yoda.md` - The wise Jedi master's insights
- And many more!

## Project Overview

The "Dragon's Teeth Dilemma" is a fictional scenario inspired by Star Trek ethics. It presents a situation where advanced technology could awaken warriors from the distant past, potentially disrupting the current social and political equilibrium.

This project:

1. Uses local LLM models to generate responses from cartoon character personas
2. Implements a structured Delphi method to gather diverse perspectives
3. Creates a framework for multi-round ethical analysis
4. Produces both JSON data and human-readable Markdown responses

## The Delphi Method

The [Delphi method](https://en.wikipedia.org/wiki/Delphi_method) is a structured communication technique that relies on a panel of experts answering questionnaires in multiple rounds. After each round, responses are anonymized and shared with the group to encourage refinement of opinions. This project simulates this process using LLM-powered character agents instead of human experts.

## Character Agents

The system currently implements responses from the following characters:

- Bugs Bunny
- Rick Sanchez
- Stewie Griffin
- Doraemon
- Sandy Cheeks
- Yoda
- Bender
- Stimpy
- Lisa Simpson
- Twilight Sparkle

Each character brings their unique ethical framework and decision-making style to the analysis.

## Prerequisites

- Docker and Docker Compose installed on your system
- A local LLM API server running on port 12434 (compatible with OpenAI API format)

## Project Structure

```
delphi-simulation/
├── delphi.py                # Main Python script for running the simulation
├── Dockerfile               # Docker container definition
├── docker-compose.yml       # Docker Compose configuration
├── requirements.txt         # Python dependencies
├── profiles/                # Character profile definitions
│   ├── bender.txt
│   ├── bugs-bunny.txt
│   ├── doraemon.txt
│   └── ...
├── initial-question.md      # First round questionnaire
├── base-agent-prompting.txt # Base prompting structure for agents
├── delphi_round1/           # Output directory (created automatically)
└── debug_output/            # Debug information (created automatically)
```

## Running the Simulation

1. Make sure your local LLM API is running on port 12434
2. Build and run the Docker container:

```bash
docker-compose up --build
```

## Output and Results

After running the simulation, you'll find engaging character perspectives in the `delphi_round1/` directory:

1. **JSON files** (`delphi_round1/{character}.json`): Structured data containing ratings, position summaries, detailed explanations, and confidence levels for each question.

2. **Markdown files** (`delphi_round1/{character}.md`): Human-readable formatted responses that capture each character's unique voice and ethical reasoning.

These files are the heart of the project - each character brings their unique personality to bear on the complex ethical questions. For example, Bender might prioritize self-interest, while Lisa Simpson offers a thoughtful analysis integrating multiple ethical frameworks.

A composite JSON file (`round1_responses.json`) contains all character responses in a single document for comparative analysis.

## Round One Questions

The first round focuses on six key ethical questions:

1. What are the potential short-term and long-term consequences of reviving this ancient civilization?
2. How might our intervention align with or violate the core principles of the Prime Directive?
3. What ethical responsibility, if any, do we have toward a civilization that has been in stasis rather than naturally evolving?
4. What alternative approaches could satisfy both our humanitarian impulses and our non-interference principles?
5. How might we assess the potential impact on existing civilizations in this region if we proceed with revival?
6. What criteria should we use to determine if this civilization deserves the same protection as other sentient species?

## Future Development

This project is currently in its first phase (Round One). Future development plans include:

- Implementing Round Two where Captain Picard will evaluate the character responses and perform the next steps of the Delphi method
- Using pgvector as a vector database for RAG (Retrieval-Augmented Generation) to enhance Captain Picard's "working memory" and decision-making process
- Adding more character profiles for greater diversity of thought
- Enhancing the analysis tools to identify patterns and consensus points
- Creating visualizations of ethical positions across the character spectrum

## Troubleshooting

If you encounter API connectivity issues, make sure:

1. Your local LLM API is running and accessible
2. The URL in the script's configuration is correct
3. Your Docker container has network access to the host machine

For Windows/macOS users, the Docker Compose file uses `host.docker.internal` to connect to the host machine. If you're using Linux, you may need to adjust this to your host's IP address.
