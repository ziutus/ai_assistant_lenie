## Running the Project with Docker

To run this project using Docker, follow the steps below:

### Prerequisites

Ensure you have Docker and Docker Compose installed on your system. Refer to the official Docker documentation for installation instructions.

### Environment Variables

Create a `.env` file in the project root directory and define the required environment variables. Refer to the `.env_example` file for the list of variables and their descriptions.

### Build and Run Instructions

1. Build the Docker images:

   ```bash
   docker-compose build
   ```

2. Start the services:

   ```bash
   docker-compose up
   ```

   This will start the application and its dependencies.

### Exposed Ports

- Application: `5000`
- Database: `5432`

Access the application at `http://localhost:5000` in your web browser.

### Additional Configuration

Ensure the PostgreSQL database is initialized with the required extensions. Connect to the database and execute:

```sql
CREATE EXTENSION vector;
```