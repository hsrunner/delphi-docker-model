# Delphi Method Simulation in Docker

This project runs the Delphi Method simulation script in a Docker container.

## Prerequisites

- Docker and Docker Compose installed on your system
- The local LLM API server running on port 12434

## Project Structure

Ensure you have the following directory structure:

```
delphi-simulation/
├── delphi.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── profiles/
│   ├── bender.txt
│   ├── bugs-bunny.txt
│   ├── doraemon.txt
│   └── ...
├── initial-question.md
├── delphi_round1/  (will be created automatically)
└── debug_output/   (will be created automatically)
```

## Running the Simulation

1. Make sure your local LLM API is running on port 12434
2. Build and run the Docker container:

```bash
docker-compose up --build
```

## Configuration

The Delphi script is configured to use a local LLM API endpoint. If you need to change any configuration parameters, modify the `CONFIG` dictionary in `delphi.py`.

## Output

Results will be written to the following directories:

- `delphi_round1/`: Contains the final JSON and Markdown responses
- `debug_output/`: Contains debug information and parsing logs

## Troubleshooting

If you encounter API connectivity issues, make sure:

1. Your local LLM API is running and accessible
2. The URL in the script's configuration is correct
3. Your Docker container has network access to the host machine

For Windows/macOS users, the Docker Compose file uses `host.docker.internal` to connect to the host machine. If you're using Linux, you may need to adjust this to your host's IP address.
