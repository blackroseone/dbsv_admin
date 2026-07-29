# DBSV Database Operations and Maintenance Tool

## Project Overview

The DBSV Database Operations and Maintenance Tool is an intelligent database operations and maintenance management platform developed by Guyunbo. The platform integrates core functional modules including Knowledge Base Management, Intelligent Q&A, SQL Tools, O&M Manuals, Command Quick Lookup, Cluster Topology, System Configuration, Log Analysis, and Intelligent O&M Agent, aiming to provide a one-stop database management solution for database administrators and operations personnel.

The platform adopts advanced RAG (Retrieval-Augmented Generation) technology combined with Large Language Model capabilities, enabling it to intelligently understand user requirements and automatically execute complex tasks such as database diagnostics, optimization, and suggestions. Through an intuitive Web interface, users can easily manage various types of databases, perform daily O&M operations, and obtain AI-driven intelligent O&M suggestions.

## Core Function Modules

### Knowledge Base Management (Knowledge Base)

The Knowledge Base module provides centralized management and intelligent retrieval functions for documents. Supporting multiple document formats (including PDF, Word, Excel, CHM, TXT, etc.), the system automatically extracts document content and performs vectorization and indexing. Users can filter knowledge documents by database type and quickly retrieve relevant materials via keywords, achieving the accumulation and inheritance of O&M experience.

### Knowledge Q&A (Q&A)

The RAG-based intelligent Q&A system understands user natural language questions, automatically retrieves relevant content from the knowledge base, and combines large language models to generate accurate and detailed answers. The system supports multi-turn dialogue, maintains dialogue context continuity, and records Q&A history for subsequent query and analysis.

### SQL Tool Module (SQL Tools)

The SQL Tool module provides comprehensive SQL operation support, including SQL syntax checking, formatting, dialect conversion, execution plans, and performance review functions. The system supports multiple database dialects (such as MySQL, PostgreSQL, Oracle, SQL Server, OceanBase, etc.) and provides intelligent SQL optimization suggestions and potential problem diagnosis through large language models.

### O&M Manuals (Manuals)

The O&M Manuals module is used to manage various database operation manuals and best practice documents. Documents are rendered in Markdown format, supporting online preview and full-text search, helping operations personnel quickly reference and follow standard operating procedures.

### Command Quick Lookup (Commands)

The Command Quick Lookup module provides quick retrieval and reference functions for common database commands. Commands are organized by database type and classification, supporting search and quick copying, helping operations personnel quickly execute daily database operations.

### Cluster Topology (Topology)

The Cluster Topology module visualizes the hierarchical structure of the database cluster, including components such as Resource Pools, Clusters, Servers, Instances, and Tenants. Users can intuitively view the distribution relationships, hardware configurations, and running status of nodes within the cluster, supporting both statistical views and topology views.

### System Configuration (Config)

The System Configuration module provides global parameter settings and multi-model configuration management functions. It supports configuring LLM API addresses, keys, and parameters, allows adding and switching multiple AI models to meet intelligent analysis needs in different scenarios. Additionally, it provides features such as configuration import/export, log management, and feature switch configuration.

### Log Analysis (Log Analysis)

The Log Analysis module supports batch upload and intelligent analysis of database logs. The system automatically diagnoses problems in the logs through a multi-round analysis process (intent recognition, log filtering, root cause analysis), generating structured analysis reports to help operations personnel quickly locate and resolve faults.

### Intelligent O&M Agent (Intelligent Agent)

The Intelligent O&M Agent is the AI core engine of the platform, capable of autonomously understanding and executing complex database O&M tasks. Through a cycle of planning, execution, and verification, the Agent combines knowledge base retrieval and various tool calls to achieve end-to-end automated O&M. Users can describe requirements in natural language, and the Agent will automatically decompose tasks and generate executable solutions.

## Technical Architecture

### Backend Technology Stack

The backend is built using the Python Flask framework, providing RESTful API services. Core dependencies include: SQLAlchemy as the ORM layer for database operations; SQLAlchemy-Utils for type and function support; Flask-CORS for handling cross-origin requests; python-LLMSample-sdk or similar SDK for LLM invocation. Data persistence uses a lightweight SQLite database, managing database structure changes via migration scripts.

### Frontend Technology Stack

The frontend is built using native HTML/CSS/JavaScript to construct a Single Page Application (SPA), implementing modular page switching and interaction. CSS uses CSS variables to implement dark theme support and responsive layouts adapting to different screen sizes. JavaScript modules are divided by function, including application initialization, API request encapsulation, controllers for each functional module, etc., achieving inter-component communication via event driving.

### RAG Vector Search

Knowledge retrieval adopts a vector-based semantic search scheme. Pre-trained language models are used to convert text snippets into high-dimensional vectors, stored in a vector database. During queries, user questions are similarly converted into vectors, and semantic matching is performed via cosine similarity calculation, returning the most relevant knowledge snippets for the LLM to reference.

### AI Agent Engine

The Intelligent Agent engine adopts the ReAct (Reasoning and Acting) pattern. After receiving a user question, the Agent first retrieves relevant background knowledge from the knowledge base, then analyzes the question and plans execution steps within a Chain of Thought, and finally completes specific tasks by calling tools (such as database queries, command execution, knowledge retrieval, etc.). The system has built-in multiple security verification mechanisms to ensure operations do not exceed preset permission scopes.

## Directory Structure

```
dbsv_admin/
├── app.py                  # Application factory function and startup entry
├── config.py               # Configuration file
├── sql_checker.py          # SQL syntax checker
├── utils.py                # Utility function collection
├── deploy.md               # Deployment guide
├── version_update.md       # Version update log
├── code_desc.md            # Code structure documentation
├── tables_desc.md          # Database table structure documentation
├── db/
│   ├── __init__.py         # Database module initialization
│   ├── database.py         # Database management layer (connections, configuration, operation functions)
│   └── migration.py        # Data migration scripts
├── rag/
│   ├── __init__.py         # RAG module initialization
│   └── embedder.py         # Vector embedding and retrieval implementation
├── agent/
│   ├── __init__.py         # Agent module initialization
│   ├── engine.py           # Agent core engine (SmartOpsAgent)
│   ├── harness.py          # Security constraint framework
│   ├── skills.py           # Domain knowledge and operational skills
│   ├── state.py            # Agent state management
│   └── tools.py            # MCP-style tool definitions
├── routes/
│   ├── __init__.py         # Blueprint route export
│   ├── agent.py            # Agent core API
│   ├── agent_connections.py # Agent connection management API
│   ├── commands.py         # Command quick lookup API
│   ├── config.py           # System configuration API
│   ├── dashboard.py        # Dashboard API
│   ├── db_types.py         # Database type management API
│   ├── knowledge.py        # Knowledge Base file management API
│   ├── log_analysis.py     # Log analysis API
│   ├── manuals.py          # O&M Manual API
│   ├── qa.py               # Knowledge Q&A API
│   ├── sql_tools.py        # SQL Tool API
│   └── topology.py         # Cluster Topology API
├── static/
│   ├── css/
│   │   └── style.css       # Frontend stylesheet
│   └── js/
│       ├── api.js          # API request encapsulation
│       ├── app.js          # Frontend entry and global controller
│       ├── agent.js        # Intelligent O&M Agent module
│       ├── commands.js     # Command quick lookup module
│       ├── config.js       # System configuration module
│       ├── knowledge.js    # Knowledge Base module
│       ├── log-analysis.js # Log analysis module
│       ├── manuals.js      # O&M Manual module
│       ├── qa.js           # Knowledge Q&A module
│       ├── sql-tools.js    # SQL Tool module
│       ├── topology.js     # Cluster Topology module
│       └── utils.js        # General utility functions
├── templates/
│   └── index.html          # SPA main page
└── docs/
    ├── feature_config_plan.md  # Feature configuration switch implementation plan
    └── log_analysis_design.md  # Log analysis function design proposal
```

## Deployment Guide

### Environment Requirements

The deployment environment must meet the following requirements: Operating systems supported include Linux (recommended), Windows, and macOS; Python version 3.8 or above; Recommended memory 4GB or more, disk space 10GB or more; Internet connection required to download dependency packages and model files.

### Install Dependencies

It is recommended to use a virtual environment to isolate project dependencies. First create and activate the virtual environment, then execute the following command in the project root directory to install dependency packages:

```bash
# Create virtual environment (Windows)
python -m venv venv
venv\Scripts\activate

# Create virtual environment (Linux/macOS)
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Startup Methods

Development mode is suitable for debugging and development testing, starting with the Flask built-in server:

```bash
# Windows
python app.py

# Linux/macOS
python3 app.py
```

For production environments, it is recommended to use Gunicorn (Linux) or Waitress (Windows) as the WSGI server:

```bash
# Linux Production Mode
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Windows Production Mode
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

### First Startup

Upon first startup, the system will automatically create the SQLite database file (dbsv.db) and execute data migrations. If LLM API configuration is required, please refer to the configuration instructions in the Deployment Guide.

For detailed deployment steps, systemd service configuration, Nginx reverse proxy, and firewall settings, please refer to the `deploy.md` file.

## API Documentation

### Knowledge Base Interfaces

The Knowledge Base module provides interfaces for file management, retrieval, and index rebuilding. Upload files using `POST /api/knowledge/upload/<db_type>`, get file list using `GET /api/knowledge/files/<db_type>`, search knowledge using `POST /api/knowledge/search`. Index management interfaces include rebuild all indexes `POST /api/knowledge/reindex` and rebuild single file index `POST /api/knowledge/reindex/file`.

### Knowledge Q&A Interfaces

The Q&A module supports session management and message interaction. Create session using `POST /api/qa/conversations`, send question using `POST /api/qa/ask`, streaming response using `POST /api/qa/ask/stream`. History record query supports getting messages by session ID and getting all session list.

### SQL Tool Interfaces

The SQL Tool module provides multiple operation interfaces. SQL formatting using `POST /api/sql/format`, SQL conversion using `POST /api/sql/convert`, SQL explanation using `POST /api/sql/explain`, SQL review using `POST /api/sql/review`. All interfaces support streaming response mode.

### Cluster Topology Interfaces

The Topology module provides management interfaces for Resource Pools, Clusters, Servers, Instances, and Tenants. Resource pool management using `GET/POST /api/topology/resource-pools`, Cluster management using `GET/POST /api/topology/clusters`. Statistical view interface `GET /api/topology/stats` returns cluster overview data, export interface `GET /api/topology/export` supports exporting topology structure.

### System Configuration Interfaces

The Configuration module manages LLM models and system parameters. Get model list using `GET /api/config/llm/models`, save model using `POST /api/config/llm/models`, set default model using `POST /api/config/llm/models/<model_id>/default`. Feature configuration using `GET /api/config/features` and `PUT /api/config/features/<module_id>`.

### Agent Interfaces

The Agent module provides session management and task execution interfaces. Create session using `POST /api/agent/sessions`, execute task using `POST /api/agent/run`, get session steps using `GET /api/agent/sessions/<session_id>/steps`. Tool list using `GET /api/agent/tools`, skill list using `GET /api/agent/skills`.

## User Instructions

### Quick Start

1. After starting the application, access `http://localhost:5000` in a browser.
2. Enter the "System Configuration" page and configure at least one LLM model connection.
3. Add database types needing management in "Database Types".
4. Upload knowledge documents to "Knowledge Base" and execute index rebuilding.
5. Start using various functional modules for database O&M work.

### Using Knowledge Base

In the Knowledge Base module, after selecting a database type, you can view all knowledge documents for that type. After uploading new documents, the system will automatically extract content and perform preprocessing. The search function supports keyword retrieval, and results will display relevance scores. Administrators can manage file tags, bookmark favorite documents, and execute batch index rebuilding.

### Using Intelligent Q&A

In the Q&A module, you can select an existing session or create a new one. After entering a question, choose whether to use Knowledge Base enhancement (RAG) and whether to reference cluster topology information. The system supports streaming output, and references in the answer will mark the knowledge source. Historical sessions are saved in the sidebar and can be reviewed at any time.

### Using SQL Tools

The SQL Tool module provides four functional tabs. The Formatting tab can standardize SQL code; the Conversion tab supports SQL conversion between different database dialects; the Explanation tab displays execution plans and optimization suggestions; the Review tab provides comprehensive SQL quality checks and performance optimization suggestions.

### Using Cluster Topology

The Topology module supports two display modes: Statistical View and Graphical View. The Statistical View displays the overall cluster status in tables and charts, supporting multi-dimensional filtering; the Graphical View displays the hierarchical relationship of Resource Pools, Clusters, and Servers in a tree structure, supporting expand/collapse and node detail viewing.

### Using Intelligent Agent

In the Agent module, first configure SSH connections (for executing commands) and database connections (for executing SQL). After creating a session, select a connection and enter O&M requirements. The Agent will automatically analyze the problem, execute operations, and return results, supporting viewing execution steps, intermediate thought processes, and tool call details.

## Version History

Current Version: v2.5.1 (2026-07-28)

Latest version updates include Knowledge Base RAG optimization, Knowledge Q&A frontend optimization, Dashboard improvements, and Reindex interface refactoring. For major functional update history, please refer to the `version_update.md` file.

## License

This project is open-source software; please comply with relevant open-source agreements for use.

## Contributors

Developer: Guyunbo