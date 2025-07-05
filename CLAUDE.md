# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
- `source env.sh` - Activate conda environment (bp-trader)
- `pip install -r requirements.txt` - Install Python dependencies

### Testing
- No specific tests currently implemented

### Docker Operations
- `docker-compose up --build -d` - Build and start services in detached mode
- `docker-compose down` - Stop and remove containers
- `./rebuild.sh` - Full rebuild: stop containers, remove images, and rebuild

### Application
- `python main.py` - Start the automated trading application

## Architecture Overview

This is a Python-based automated trading application for Backpack Exchange with the following structure:

### Core Components
- **main.py**: Application entry point that runs automated trading loop
- **config/config.py**: Centralized configuration management with environment-specific .env file loading
- **service/**: Trading and API services
  - **backpack_client.py**: Backpack Exchange API client with ED25519 authentication
  - **trading_service.py**: Automated trading logic implementation
- **utils/**: Utility modules
  - **logger.py**: Structured logging setup

### Infrastructure
- Lightweight application with minimal dependencies
- Docker containerization with docker-compose
- Environment-based configuration (dev/prod)

### Key Patterns
- ED25519 cryptographic signing for API authentication
- Chinese comments throughout the codebase
- Structured logging with custom logger setup
- Environment variable configuration with .env file support

### Trading Logic
The application implements automated trading with the following behavior:
1. **Position Monitoring**: Continuously checks for existing positions in the configured trading symbol
2. **Automatic Close**: If any position exists, immediately closes it at market price
3. **Order Management**: If no position exists and no open orders, places a limit buy order at best bid price
4. **Configurable Parameters**: Trading symbol, leverage, and trade amount are configurable via environment variables

### Environment Variables Required
- `BACKPACK_API_KEY`, `BACKPACK_PRIVATE_KEY` (Base64 encoded ED25519 keys)
- `TRADING_SYMBOL` (default: SOL), `TRADING_LEVERAGE` (default: 10), `TRADING_AMOUNT` (default: 100.0)
- `ENV` (dev/prod)