# CircleCI Pattern

Example CircleCI configuration with a self-hosted runner on EC2.

> **Parent document:** [CI_CD.md](CI_CD.md) — general CI/CD pipeline rules and conventions.

## Architecture

```
start-ec2
    ↓
run-job-on-ec2 (tests)
    ↓
run-job-on-ec2-docker (build)
    ↓
stop-ec2
```

## Orbs and Executors

```yaml
orbs:
  aws-cli: circleci/aws-cli@3.1    # AWS CLI integration

executors:
  python-executor:                  # Lightweight Python container
    docker:
      - image: cimg/python:3.11

  machine-executor:                 # Machine with Docker
    machine:
      docker_layer_caching: true    # Docker layer cache
```

## Jobs

### 1. start-ec2
Starts the EC2 instance before running tests.

```yaml
jobs:
  start-ec2:
    executor: python-executor
    steps:
      - aws-cli/setup
      - run:
          name: "Start EC2 instances"
          command: |
            aws ec2 start-instances --instance-ids $INSTANCE_ID
```

### 2. run-job-on-ec2
Installs dependencies and runs tests on the self-hosted EC2 runner.

```yaml
run-job-on-ec2:
  executor: machine-executor
  resource_class: itsnap/itsnap-runner    # Self-hosted runner
  steps:
    - checkout
    - run:
        name: "Install uv and dependencies"
        command: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          export PATH="$HOME/.cargo/bin:$PATH"
          uv venv venv
          . venv/bin/activate
          uv pip install -r backend/requirements_server.txt
    - run:
        name: "Run tests"
        command: |
          . venv/bin/activate
          mkdir -p test-results
          python -m pytest tests/unit --junitxml=test-results/results.xml || true
    - store_test_results:
        path: test-results/results.xml
```

**Notes:**
- Uses `uv venv` instead of `--system` (isolated environment)
- Generates report in JUnit XML format
- Unit tests only (`tests/unit`)

### 3. run-job-on-ec2-docker
Builds Docker image on the self-hosted runner.

```yaml
run-job-on-ec2-docker:
  executor: machine-executor
  resource_class: itsnap/itsnap-runner
  steps:
    - checkout
    - run:
        name: "Execute job on EC2"
        command: |
          docker build -t lenie-ai-server:latest .
```

### 4. stop-ec2
Stops the EC2 instance after the pipeline completes.

```yaml
stop-ec2:
  executor: python-executor
  steps:
    - aws-cli/setup
    - run:
        name: "Stop EC2 instances"
        command: |
          aws ec2 stop-instances --instance-ids $INSTANCE_ID
```

## Workflow

```yaml
workflows:
  ec2-workflow:
    jobs:
      - start-ec2:
          filters:
            branches:
              only: [main, dev]
      - run-job-on-ec2:
          requires: [start-ec2]
          filters:
            branches:
              only: [main, dev]
      - run-job-on-ec2-docker:
          requires: [run-job-on-ec2]
          filters:
            branches:
              only: [main, dev]
      - stop-ec2:
          requires: [run-job-on-ec2-docker]
          filters:
            branches:
              only: [main, dev]
```

## Self-hosted Runner

CircleCI uses a self-hosted runner on EC2:
- **Resource class:** `itsnap/itsnap-runner`
- Runner must be installed on the EC2 instance
- Documentation: https://circleci.com/docs/runner-overview/

## Storing Test Results

```yaml
- store_test_results:
    path: test-results/results.xml
```

CircleCI automatically parses JUnit XML format and displays results in the UI.
